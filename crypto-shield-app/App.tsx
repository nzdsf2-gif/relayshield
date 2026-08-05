import "./src/polyfills";
import React, { useState, useEffect } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createStackNavigator } from "@react-navigation/stack";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { Text, View, ActivityIndicator } from "react-native";
import * as SecureStore from "expo-secure-store";
import { DashboardScreen } from "./src/screens/DashboardScreen";
import { WalletsScreen } from "./src/screens/WalletsScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";
import { ScanScreen } from "./src/screens/ScanScreen";
import { SupplyChainScreen } from "./src/screens/SupplyChainScreen";
import { IntelScreen } from "./src/screens/IntelScreen";
import { SignaturePoisoningScreen } from "./src/screens/SignaturePoisoningScreen";
import { useMonthlyLinkedDevicePush } from "./src/hooks/useMonthlyPush";
import { usePushNotifications } from "./src/hooks/usePushNotifications";
import { useWallets } from "./src/hooks/useWallet";
import { OnboardingScreen } from "./src/screens/OnboardingScreen";
import { PaywallScreen } from "./src/screens/PaywallScreen";
import { ErrorBoundary } from "./src/components/ErrorBoundary";
import { TourOverlay } from "./src/components/TourOverlay";
import { UpdateNudge } from "./src/components/UpdateNudge";
import { useUpdateCheck } from "./src/hooks/useUpdateCheck";
import { useSubscriptionDeepLink } from "./src/hooks/useSubscriptionDeepLink";

const Tab   = createBottomTabNavigator();
const Stack = createStackNavigator();

function TourScreen({ navigation }: any) {
  return (
    <TourOverlay
      visible={true}
      onDone={() => {
        SecureStore.setItemAsync("cs_tour_done", "true");
        navigation.goBack();
      }}
    />
  );
}

function withErrorBoundary(Component: React.ComponentType, name: string) {
  return function BoundedScreen(props: any) {
    return (
      <ErrorBoundary screenName={name}>
        <Component {...props} />
      </ErrorBoundary>
    );
  };
}

function TabIcon({ emoji, focused }: { emoji: string; focused: boolean }) {
  return <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>{emoji}</Text>;
}

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: "#0F1F3D",
          borderTopColor: "#1e3a5f",
          borderTopWidth: 1,
          paddingBottom: 6,
          paddingTop: 6,
          height: 60,
        },
        tabBarActiveTintColor: "#00B5A5",
        tabBarInactiveTintColor: "#64748b",
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
      }}
    >
      <Tab.Screen
        name="Dashboard" component={withErrorBoundary(DashboardScreen, "Dashboard")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="🛡" focused={focused} />, tabBarLabel: "Shield" }}
      />
      <Tab.Screen
        name="Wallets" component={withErrorBoundary(WalletsScreen, "Wallets")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="💼" focused={focused} />, tabBarLabel: "Wallets" }}
      />
      <Tab.Screen
        name="Scan" component={withErrorBoundary(ScanScreen, "Scan")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="🔍" focused={focused} />, tabBarLabel: "Scan" }}
      />
      <Tab.Screen
        name="Vendors" component={withErrorBoundary(SupplyChainScreen, "Vendors")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="🔗" focused={focused} />, tabBarLabel: "Vendors" }}
      />
      <Tab.Screen
        name="Intel" component={withErrorBoundary(IntelScreen, "Intel")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="📊" focused={focused} />, tabBarLabel: "Intel" }}
      />
      <Tab.Screen
        name="SigGuard" component={withErrorBoundary(SignaturePoisoningScreen, "SigGuard")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="🎯" focused={focused} />, tabBarLabel: "Tools" }}
      />
      <Tab.Screen
        name="Settings" component={withErrorBoundary(SettingsScreen, "Settings")}
        options={{ tabBarIcon: ({ focused }) => <TabIcon emoji="⚙️" focused={focused} />, tabBarLabel: "Settings" }}
      />
    </Tab.Navigator>
  );
}

export default function App() {
  const [booted,          setBooted]          = useState(false);
  const [onboarded,       setOnboarded]       = useState(false);
  const [showTour,        setShowTour]        = useState(false);
  const [nftCollections,  setNftCollections]  = useState<string[]>([]);
  useMonthlyLinkedDevicePush();
  const { updateAvailable, latestVersion, dismiss } = useUpdateCheck();
  const { apiKey, wallets, saveApiKey } = useWallets();
  useSubscriptionDeepLink(saveApiKey);
  usePushNotifications(
    apiKey,
    wallets.map(w => w.address),
    undefined,
    undefined,
    nftCollections,
  );

  useEffect(() => {
    SecureStore.getItemAsync("cs_onboarded").then(v => {
      setOnboarded(v === "true");
      setBooted(true);
    });
    SecureStore.getItemAsync("cs_tour_done").then(v => {
      if (v !== "true") setShowTour(true);
    });
    SecureStore.getItemAsync("cs_nft_collections").then(v => {
      if (v) {
        try {
          const parsed = JSON.parse(v);
          setNftCollections(parsed.map((c: any) => c.contract ?? c.id ?? "").filter(Boolean));
        } catch {}
      }
    });
  }, []);

  if (!booted) {
    return (
      <View style={{ flex: 1, backgroundColor: "#0a1628", alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color="#00B5A5" size="large" />
      </View>
    );
  }

  if (!onboarded) {
    return (
      <SafeAreaProvider>
        <ErrorBoundary screenName="Onboarding">
          <OnboardingScreen onComplete={() => { setOnboarded(true); setShowTour(true); }} />
        </ErrorBoundary>
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: "#00B5A5",
            background: "#0a1628",
            card: "#0F1F3D",
            text: "#e2e8f0",
            border: "#1e3a5f",
            notification: "#ef4444",
          },
        }}
      >
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Main" component={MainTabs} />
          <Stack.Screen
            name="Paywall"
            component={PaywallScreen}
            options={{ presentation: "modal" }}
          />
          <Stack.Screen
            name="Tour"
            component={TourScreen}
            options={{ presentation: "transparentModal" }}
          />
        </Stack.Navigator>
        <TourOverlay
          visible={showTour}
          onDone={() => {
            setShowTour(false);
            SecureStore.setItemAsync("cs_tour_done", "true");
          }}
        />
        {updateAvailable && latestVersion && !showTour && (
          <UpdateNudge latestVersion={latestVersion} onDismiss={dismiss} />
        )}
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
