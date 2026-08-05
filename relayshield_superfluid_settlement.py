"""
RelayShield — Superfluid Weekly Settlement
EventBridge rate(7 days) → this Lambda

Steps:
  1. Check USDCx balance in RS self-custody wallet
  2. If above $5 threshold, unwrap USDCx → USDC (Superfluid downgrade())
  3. Send USDC to CB Business USDC deposit address (auto-converts to USD, free, 1:1)
  4. Manual step (2 clicks): CB Business Home → Withdraw cash → Relay Financial

Requires: web3.py Lambda layer
  pip install web3 -t python/
  zip -r web3-layer.zip python/
  aws lambda publish-layer-version --layer-name relayshield-web3 --zip-file fileb://web3-layer.zip \
      --compatible-runtimes python3.12 --profile relayshield

Secrets required (add before deploying):
  relayshield/rs_wallet_private_key  — private key for 0x002CfD89...12bAc
  relayshield/alchemy_api_key        — already exists

TODOs before first deploy:
  1. Verify USDCX_ADDRESS at https://explorer.superfluid.org/base-mainnet
  2. Get CB_DEPOSIT_ADDR from CB Business → Receive crypto → USDC on Base
  3. Add rs_wallet_private_key to Secrets Manager
  4. Build and attach web3.py Lambda layer
"""

import json
import boto3
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Config ─────────────────────────────────────────────────────────────────────

ALCHEMY_BASE_RPC = 'https://base-mainnet.g.alchemy.com/v2'
RS_WALLET        = '0x002CfD89c5636F45E3C8576D6E35154748412bAc'

# USDC on Base Mainnet (verified — Circle official)
USDC_ADDRESS  = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'

# USDCx on Base Mainnet — verified June 5 2026 at explorer.superfluid.org (checkmark badge)
USDCX_ADDRESS = '0xD04383398dD2426297da660F9CCA3d439AF9ce1b'

# CB Business USDC deposit address on Base — confirmed June 5 2026
CB_DEPOSIT_ADDR = '0x07029b0AFC1624C9263Ce0Be8641A4c3709C5632'

# Base mainnet chain ID
BASE_CHAIN_ID = 8453

# Only settle if balance > $5 (avoids dust txs with gas overhead)
SETTLEMENT_THRESHOLD_UNITS = 5 * 10 ** 6  # 5 USDC in 6-decimal units

# Minimal ABIs
USDCX_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "downgrade",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs":  [{"name": "amount", "type": "uint256"}],
        "outputs": []
    },
]

USDC_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs":  [
            {"name": "to",     "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "outputs": [{"name": "", "type": "bool"}]
    },
]

# ── Secrets ─────────────────────────────────────────────────────────────────────

secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
_cache = {}

def get_secret(key):
    if key in _cache:
        return _cache[key]
    resp = secrets_client.get_secret_value(SecretId=key)
    val  = resp.get('SecretString', '')
    try:
        result = json.loads(val).get(key.split('/')[-1], val)
    except Exception:
        result = val
    _cache[key] = result
    return result

# ── Helpers ────────────────────────────────────────────────────────────────────

def send_signed_tx(w3, account, tx):
    """Sign and broadcast a transaction, wait for receipt."""
    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise Exception(f"Transaction reverted: {tx_hash.hex()}")
    logger.info(f"TX confirmed: {tx_hash.hex()} block={receipt.blockNumber}")
    return receipt

def get_gas_params(w3):
    """Get current Base gas prices with 2x buffer for priority."""
    base_fee = w3.eth.gas_price
    return {
        'maxFeePerGas':         base_fee * 2,
        'maxPriorityFeePerGas': w3.to_wei('0.001', 'gwei'),
    }

# ── Handler ────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    """
    Weekly settlement job: unwrap accumulated USDCx → USDC → send to CB Business.
    After this runs, manually click 'Withdraw cash' in CB Business to sweep to Relay Financial.
    (Automate at 10+ subscribers via CB API)
    """
    try:
        from web3 import Web3

        alchemy_key = get_secret('relayshield/alchemy_api_key')
        private_key = get_secret('relayshield/rs_wallet_private_key')

        w3 = Web3(Web3.HTTPProvider(f'{ALCHEMY_BASE_RPC}/{alchemy_key}'))
        if not w3.is_connected():
            raise Exception("Cannot connect to Alchemy Base RPC")

        account     = w3.eth.account.from_key(private_key)
        rs_checksum = Web3.to_checksum_address(RS_WALLET)

        # ── Step 1: Check USDCx balance ────────────────────────────────────────
        usdcx = w3.eth.contract(
            address=Web3.to_checksum_address(USDCX_ADDRESS),
            abi=USDCX_ABI
        )
        usdcx_balance = usdcx.functions.balanceOf(rs_checksum).call()
        usdcx_usd     = usdcx_balance / 10 ** 6

        logger.info(f"USDCx balance: ${usdcx_usd:.4f}")

        if usdcx_balance < SETTLEMENT_THRESHOLD_UNITS:
            logger.info(f"Balance ${usdcx_usd:.2f} below $5 threshold — skipping")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'skipped', 'balance_usd': usdcx_usd})
            }

        nonce      = w3.eth.get_transaction_count(account.address)
        gas_params = get_gas_params(w3)

        # ── Step 2: Unwrap USDCx → USDC ───────────────────────────────────────
        logger.info(f"Unwrapping ${usdcx_usd:.2f} USDCx → USDC")
        unwrap_tx = usdcx.functions.downgrade(usdcx_balance).build_transaction({
            'from':    account.address,
            'nonce':   nonce,
            'gas':     200_000,
            'chainId': BASE_CHAIN_ID,
            **gas_params,
        })
        send_signed_tx(w3, account, unwrap_tx)

        # ── Step 3: Check USDC balance post-unwrap ────────────────────────────
        usdc = w3.eth.contract(
            address=Web3.to_checksum_address(USDC_ADDRESS),
            abi=USDC_ABI
        )
        usdc_balance = usdc.functions.balanceOf(rs_checksum).call()
        usdc_usd     = usdc_balance / 10 ** 6
        logger.info(f"USDC balance after unwrap: ${usdc_usd:.4f}")

        # ── Step 4: Send USDC to CB Business ──────────────────────────────────
        logger.info(f"Sending ${usdc_usd:.2f} USDC to CB Business deposit address")
        nonce      = w3.eth.get_transaction_count(account.address)
        gas_params = get_gas_params(w3)

        transfer_tx = usdc.functions.transfer(
            Web3.to_checksum_address(CB_DEPOSIT_ADDR),
            usdc_balance
        ).build_transaction({
            'from':    account.address,
            'nonce':   nonce,
            'gas':     100_000,
            'chainId': BASE_CHAIN_ID,
            **gas_params,
        })
        send_signed_tx(w3, account, transfer_tx)

        logger.info(
            f"✅ Settlement complete: ${usdc_usd:.2f} USDC sent to CB Business\n"
            f"   NEXT: Log in to CB Business → Withdraw cash → Relay Financial"
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'status':        'settled',
                'settled_usd':   round(usdc_usd, 2),
                'timestamp':     datetime.now(timezone.utc).isoformat(),
                'next_step':     'Withdraw cash from CB Business to Relay Financial (manual)'
            })
        }

    except ImportError:
        logger.error("web3 not available — attach the relayshield-web3 Lambda layer")
        return {'statusCode': 500, 'body': 'web3 layer not attached'}

    except Exception as e:
        logger.error(f"Settlement error: {e}", exc_info=True)
        return {'statusCode': 500, 'body': str(e)}
