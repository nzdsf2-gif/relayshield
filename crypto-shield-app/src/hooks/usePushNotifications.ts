// OS-level push notification registration and handler
// Wires Expo Push Token to RS backend so server-side alerts fire on device

import { useEffect, useRef } from "react";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
import Constants from "expo-constants";
import * as RS from "../api/relayshield";

export const PUSH_TOKEN_KEY = "cs_expo_push_token";
const PUSH_REGISTERED_KEY = "cs_push_registered_at";
export const LAST_ALERT_KEY = "cs_last_alert";

// How notifications appear when the app is in the foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge:  true,
  }),
});

export function usePushNotifications(
  apiKey: string | null,
  walletAddresses: string[],
  onNotificationReceived?: (notification: Notifications.Notification) => void,
  onNotificationResponse?: (response: Notifications.NotificationResponse) => void,
  nftCollections: string[] = [],
) {
  const notifListener  = useRef<any>();
  const responseListener = useRef<any>();

  useEffect(() => {
    registerForPushNotifications(apiKey, walletAddresses, nftCollections);

    // Fired when a notification arrives while the app is open
    notifListener.current = Notifications.addNotificationReceivedListener(notif => {
      SecureStore.setItemAsync(LAST_ALERT_KEY, JSON.stringify({
        title: notif.request.content.title ?? "",
        body: notif.request.content.body ?? "",
        timestamp: new Date().toISOString(),
      })).catch(() => {});
      onNotificationReceived?.(notif);
    });

    // Fired when user taps the notification
    responseListener.current = Notifications.addNotificationResponseReceivedListener(resp => {
      onNotificationResponse?.(resp);
    });

    return () => {
      Notifications.removeNotificationSubscription(notifListener.current);
      Notifications.removeNotificationSubscription(responseListener.current);
    };
  }, [apiKey, walletAddresses.join(",")]);
}

async function registerForPushNotifications(
  apiKey: string | null,
  walletAddresses: string[],
  nftCollections: string[] = [],
): Promise<void> {
  // Request OS permission
  const { status: existing } = await Notifications.getPermissionsAsync();
  let finalStatus = existing;

  if (existing !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== "granted") return;

  // Android: create notification channel
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "CryptoShield Alerts",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#00B5A5",
    });
    await Notifications.setNotificationChannelAsync("critical", {
      name: "Critical Security Alerts",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 500, 250, 500],
      lightColor: "#ef4444",
      sound: "default",
    });
  }

  // Get Expo push token
  const projectId: string | undefined =
    (Constants.easConfig as any)?.projectId ??
    (Constants.expoConfig as any)?.extra?.eas?.projectId;
  if (!projectId) return; // Expo Go dev — skip until EAS project is registered

  let token: string;
  try {
    const result = await Notifications.getExpoPushTokenAsync({ projectId });
    token = result.data;
  } catch {
    return;
  }

  // Check if already registered with this token
  const storedToken     = await SecureStore.getItemAsync(PUSH_TOKEN_KEY);
  const lastRegistered  = await SecureStore.getItemAsync(PUSH_REGISTERED_KEY);
  const oneDayAgo       = Date.now() - 86400000;
  const alreadyCurrent  = storedToken === token &&
    lastRegistered && parseInt(lastRegistered) > oneDayAgo;

  if (alreadyCurrent) return;

  // Register with RS backend
  if (apiKey) {
    try {
      await RS.registerPushToken(token, walletAddresses, apiKey, nftCollections);
      await SecureStore.setItemAsync(PUSH_TOKEN_KEY,      token);
      await SecureStore.setItemAsync(PUSH_REGISTERED_KEY, String(Date.now()));
    } catch {
      // Silent fail — retry next launch
    }
  } else {
    // Store token locally even without API key — register when key is added
    await SecureStore.setItemAsync(PUSH_TOKEN_KEY, token);
  }
}

// Utility: send a local notification immediately (for testing or in-app alerts)
export async function sendLocalNotification(
  title: string,
  body: string,
  data?: object,
  channel: "default" | "critical" = "default",
) {
  await Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      data:  data || {},
      sound: "default",
      ...(Platform.OS === "android" && { channelId: channel }),
    },
    trigger: null, // fire immediately
  });
}
