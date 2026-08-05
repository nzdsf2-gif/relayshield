// Monthly linked-device audit push notification
// Schedules a push on the 1st of each month reminding users to audit linked devices

import { useEffect } from "react";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";

const LAST_MONTHLY_PUSH_KEY = "cs_last_monthly_push";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

export function useMonthlyLinkedDevicePush() {
  useEffect(() => {
    scheduleMontlyPushIfDue();
  }, []);
}

async function scheduleMontlyPushIfDue() {
  // Check if we already scheduled one this month
  const lastPush = await SecureStore.getItemAsync(LAST_MONTHLY_PUSH_KEY);
  const now = new Date();
  const thisMonth = `${now.getFullYear()}-${now.getMonth()}`;

  if (lastPush === thisMonth) return; // already scheduled this month

  // Request permission
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== "granted") return;

  // Cancel any existing scheduled monthly push
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  for (const notif of scheduled) {
    if (notif.content.data?.type === "monthly_linked_device_audit") {
      await Notifications.cancelScheduledNotificationAsync(notif.identifier);
    }
  }

  // Schedule for 1st of next month at 9 AM
  const nextFirst = new Date(now.getFullYear(), now.getMonth() + 1, 1, 9, 0, 0);

  await Notifications.scheduleNotificationAsync({
    content: {
      title: "🔗 Monthly Security Check",
      body: "Audit your linked devices on Telegram, WhatsApp & Signal — takes 2 minutes. Tap to open.",
      data: { type: "monthly_linked_device_audit", screen: "Wallets" },
    },
    trigger: { date: nextFirst },
  });

  await SecureStore.setItemAsync(LAST_MONTHLY_PUSH_KEY, thisMonth);
}
