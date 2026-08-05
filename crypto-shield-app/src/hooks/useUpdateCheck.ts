import { useState, useEffect } from "react";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";
import { getCSMobileLatestVersion } from "../api/relayshield";

const CHECK_ENABLED_KEY = "cs_update_check_enabled";
const DISMISSED_VERSION_KEY = "cs_update_dismissed_version";

function isNewer(latest: string, current: string): boolean {
  const l = latest.split(".").map(Number);
  const c = current.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if ((l[i] ?? 0) > (c[i] ?? 0)) return true;
    if ((l[i] ?? 0) < (c[i] ?? 0)) return false;
  }
  return false;
}

export function useUpdateCheck() {
  const [latestVersion, setLatestVersion] = useState<string | null>(null);
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null);
  const [checkEnabled, setCheckEnabledState] = useState(true);

  const currentVersion = Constants.expoConfig?.version ?? "0.0.0";

  useEffect(() => {
    (async () => {
      const enabledStored = await SecureStore.getItemAsync(CHECK_ENABLED_KEY);
      const enabled = enabledStored !== "false"; // default on
      setCheckEnabledState(enabled);
      if (!enabled) return;

      const dismissed = await SecureStore.getItemAsync(DISMISSED_VERSION_KEY);
      setDismissedVersion(dismissed);

      const latest = await getCSMobileLatestVersion();
      if (latest) setLatestVersion(latest);
    })();
  }, []);

  async function setCheckEnabled(value: boolean) {
    setCheckEnabledState(value);
    await SecureStore.setItemAsync(CHECK_ENABLED_KEY, value ? "true" : "false");
  }

  async function dismiss() {
    if (!latestVersion) return;
    setDismissedVersion(latestVersion);
    await SecureStore.setItemAsync(DISMISSED_VERSION_KEY, latestVersion);
  }

  const updateAvailable =
    checkEnabled &&
    !!latestVersion &&
    isNewer(latestVersion, currentVersion) &&
    latestVersion !== dismissedVersion;

  return { updateAvailable, latestVersion, currentVersion, checkEnabled, setCheckEnabled, dismiss };
}
