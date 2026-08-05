"""
RelayShield — Superfluid Webhook Handler
Triggered by Alchemy Notify when Superfluid CFA contract emits FlowUpdated events on Base.

Flow:
  FlowCreated (rate >= MIN_FLOW_RATE) → activate Crypto Shield subscription + Telegram welcome
  FlowDeleted (rate == 0)            → deactivate subscription + Telegram notification
  FlowUpdated (rate < MIN_FLOW_RATE) → treat as cancellation (downgrade below threshold)

VERIFY before deployment:
  USDCX_ADDRESS    — check https://explorer.superfluid.org/base-mainnet → Tokens
  FLOW_UPDATED_TOPIC — confirm event signature hash matches Superfluid v1 CFA on Base

Alchemy Notify setup:
  Webhook type: GraphQL Custom Webhook
  Network: Base Mainnet
  Filter: logs from SUPERFLUID_CFA_ADDRESS where topics[3] == RS_WALLET (receiver, indexed)
"""

import json
import boto3
import hashlib
import hmac
import logging
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Constants ──────────────────────────────────────────────────────────────────

# Superfluid CFA v1 (Constant Flow Agreement) — Base Mainnet
# This is the contract that EMITS FlowUpdated events — NOT the forwarder
# Source: @superfluid-finance/metadata — verified June 5 2026
# cfaV1Forwarder (do NOT monitor this): 0xcfA132E353cB4E398080B9700609bb008eceB125
SUPERFLUID_CFA_ADDRESS = '0x19ba78B9cDB05A877718841c574325fdB53601bb'

# USDCx (Super Token wrapper for USDC) on Base Mainnet
# Verified June 5 2026 at explorer.superfluid.org/base-mainnet — checkmark badge confirmed
USDCX_ADDRESS = '0xD04383398dD2426297da660F9CCA3d439AF9ce1b'

# RelayShield receiving wallet (self-custody Coinbase Wallet)
RS_WALLET = '0x002CfD89c5636F45E3C8576D6E35154748412bAc'

# Minimum acceptable flow rate for $19.99/month subscription
# Calculation: 19.99 * 1_000_000 (6 decimals) / 2_592_000 (30 days in seconds) = 7,711.6
# Accept >= 7,700 to handle minor rounding differences
MIN_FLOW_RATE = 7700

# Superfluid FlowUpdated event topic — keccak256("FlowUpdated(address,address,address,int96,int256,int256,bytes)")
# Computed June 5 2026 using pycryptodome keccak256 — verified against Superfluid CFA v1 ABI
FLOW_UPDATED_TOPIC = '0x57269d2ebcccecdcc0d9d2c0a0b80ead95f344e28ec20f50f709811f209d4e0e'

# ── AWS Clients ────────────────────────────────────────────────────────────────

dynamodb       = boto3.resource('dynamodb', region_name='us-east-1')
users_table    = dynamodb.Table('relayshield_users')
secrets_client = boto3.client('secretsmanager', region_name='us-east-1')

_secret_cache = {}

def get_secret(secret_name):
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]
    resp = secrets_client.get_secret_value(SecretId=secret_name)
    val = resp.get('SecretString', '')
    try:
        parsed = json.loads(val)
        result = parsed.get(secret_name.split('/')[-1], val)
    except Exception:
        result = val
    _secret_cache[secret_name] = result
    return result

# ── Signature Verification ─────────────────────────────────────────────────────

def verify_alchemy_signature(raw_body: bytes, signature: str, signing_key: str) -> bool:
    mac = hmac.new(
        signing_key.encode('utf-8'),
        msg=raw_body,
        digestmod=hashlib.sha256
    )
    return hmac.compare_digest(mac.hexdigest(), signature)

# ── ABI Decoding ───────────────────────────────────────────────────────────────

def decode_flow_updated(topics: list, data: str) -> dict:
    """
    Decode Superfluid FlowUpdated(address token, address sender, address receiver,
                                  int96 flowRate, int256 totalSenderFlowRate,
                                  int256 totalReceiverFlowRate, bytes userData)

    topics[0] = event sig hash
    topics[1] = token   (indexed)
    topics[2] = sender  (indexed)
    topics[3] = receiver (indexed)
    data      = flowRate (int96) + totalSenderFlowRate + totalReceiverFlowRate + ...
    """
    token    = '0x' + topics[1][-40:]
    sender   = '0x' + topics[2][-40:]
    receiver = '0x' + topics[3][-40:]

    raw = bytes.fromhex(data[2:] if data.startswith('0x') else data)
    flow_rate_raw = int.from_bytes(raw[:32], 'big')
    # int96 is signed — handle negative (deletion sets rate to 0, but be safe)
    if flow_rate_raw >= 2 ** 95:
        flow_rate_raw -= 2 ** 96

    return {
        'token':     token.lower(),
        'sender':    sender.lower(),
        'receiver':  receiver.lower(),
        'flow_rate': flow_rate_raw,
    }

# ── DynamoDB ───────────────────────────────────────────────────────────────────

def get_user_by_wallet(wallet: str):
    """Scan for user with matching wallet_address field."""
    resp = users_table.scan(
        FilterExpression='wallet_address = :w',
        ExpressionAttributeValues={':w': wallet.lower()}
    )
    items = resp.get('Items', [])
    return items[0] if items else None

def activate_subscription(user_id: str, wallet: str, flow_rate: int):
    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='''SET
            subscription_tier         = :tier,
            subscription_status       = :status,
            payment_method            = :method,
            superfluid_wallet         = :wallet,
            superfluid_flow_rate      = :rate,
            subscription_activated_at = :now,
            delivery_channels         = :ch
        ''',
        ExpressionAttributeValues={
            ':tier':   'crypto_shield',
            ':status': 'active',
            ':method': 'superfluid_usdc',
            ':wallet': wallet,
            ':rate':   Decimal(str(flow_rate)),
            ':now':    datetime.now(timezone.utc).isoformat(),
            ':ch':     ['telegram'],
        }
    )
    logger.info(f"Activated Crypto Shield: user={user_id} wallet={wallet} rate={flow_rate}")

def deactivate_subscription(user_id: str, wallet: str):
    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='''SET
            subscription_status       = :status,
            subscription_cancelled_at = :now
        ''',
        ExpressionAttributeValues={
            ':status': 'cancelled',
            ':now':    datetime.now(timezone.utc).isoformat(),
        }
    )
    logger.info(f"Deactivated subscription: user={user_id} wallet={wallet}")

# ── Telegram ───────────────────────────────────────────────────────────────────

def send_telegram(chat_id: str, text: str):
    token = get_secret('relayshield/telegram_bot_token')
    url   = f'https://api.telegram.org/bot{token}/sendMessage'
    data  = json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}).encode()
    req   = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error(f"Telegram send error: {e}")

def telegram_activated(user: dict):
    chat_id = user.get('telegram_chat_id')
    if not chat_id:
        return
    send_telegram(chat_id,
        "✅ *Crypto Shield Active*\n\n"
        "Your USDC stream has been detected — you're now protected.\n\n"
        "*Monitoring:*\n"
        "• Wallet transactions & counterparty risk\n"
        "• SIM swap & port-out fraud\n"
        "• Data breach & infostealer exposure\n"
        "• Domain lookalike scanning\n\n"
        "Type /status anytime to check your coverage.\n\n"
        "_To cancel: close your Superfluid stream. "
        "Monitoring stops automatically within minutes._"
    )

def telegram_cancelled(user: dict):
    chat_id = user.get('telegram_chat_id')
    if not chat_id:
        return
    send_telegram(chat_id,
        "⚠️ *Crypto Shield Deactivated*\n\n"
        "Your USDC stream was closed — monitoring has stopped.\n\n"
        "To reactivate, open a new stream of *$19.99/month* in USDCx to:\n"
        f"`{RS_WALLET}`\n\n"
        "_Your account data is preserved — reactivation is instant._"
    )

def telegram_unregistered_wallet(wallet: str):
    """Alert admin when stream arrives from unregistered wallet."""
    admin_chat_id = '1729226804'  # Andrew's Telegram chat ID
    send_telegram(admin_chat_id,
        f"⚠️ *Unregistered Superfluid Stream*\n\n"
        f"Wallet `{wallet}` opened a Crypto Shield stream but is not registered in DynamoDB.\n\n"
        "This user may have paid before completing Telegram onboarding. "
        "Check DynamoDB and manually link if needed."
    )

# ── Handler ────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    try:
        body = event.get('body', '{}')
        raw_body = body.encode() if isinstance(body, str) else json.dumps(body).encode()

        # Verify Alchemy signature
        signing_key = get_secret('relayshield/alchemy_webhook_signing_key')
        signature   = (event.get('headers') or {}).get('x-alchemy-signature', '')
        if signing_key and not verify_alchemy_signature(raw_body, signature, signing_key):
            logger.warning("Invalid Alchemy webhook signature — rejecting")
            return {'statusCode': 401, 'body': 'Unauthorized'}

        payload = json.loads(body) if isinstance(body, str) else body

        # Extract logs from Alchemy GraphQL webhook
        logs = (payload
                .get('event', {})
                .get('data', {})
                .get('block', {})
                .get('logs', []))

        for log in logs:
            topics = log.get('topics', [])
            if len(topics) < 4:
                continue

            if topics[0].lower() != FLOW_UPDATED_TOPIC.lower():
                continue

            decoded = decode_flow_updated(topics, log.get('data', '0x'))

            # Only process streams TO RelayShield wallet in USDCx
            if decoded['receiver'].lower() != RS_WALLET.lower():
                continue
            if decoded['token'].lower() != USDCX_ADDRESS.lower():
                logger.info(f"Non-USDCx stream ignored: token={decoded['token']}")
                continue

            sender    = decoded['sender']
            flow_rate = decoded['flow_rate']
            tx_hash   = log.get('transaction', {}).get('hash', 'unknown')

            logger.info(f"FlowUpdated: sender={sender} rate={flow_rate} tx={tx_hash}")

            user = get_user_by_wallet(sender)

            if flow_rate >= MIN_FLOW_RATE:
                # Active subscription-level stream
                if user:
                    activate_subscription(user['user_id'], sender, flow_rate)
                    telegram_activated(user)
                else:
                    logger.warning(f"Stream from unregistered wallet: {sender}")
                    telegram_unregistered_wallet(sender)

            elif flow_rate == 0:
                # Stream deleted
                if user:
                    deactivate_subscription(user['user_id'], sender)
                    telegram_cancelled(user)

            else:
                # Stream exists but below threshold — treat as insufficient payment
                logger.warning(f"Sub-threshold stream from {sender}: rate={flow_rate} min={MIN_FLOW_RATE}")
                if user:
                    send_telegram(user.get('telegram_chat_id', ''),
                        f"⚠️ Your USDC stream rate is below the $19.99/month minimum.\n"
                        f"Please update your stream rate to activate Crypto Shield."
                    )

        return {'statusCode': 200, 'body': 'OK'}

    except Exception as e:
        logger.error(f"Superfluid webhook error: {e}", exc_info=True)
        return {'statusCode': 500, 'body': 'Internal error'}
