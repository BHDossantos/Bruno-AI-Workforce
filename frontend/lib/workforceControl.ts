type Control = { mode: string; autopilot: boolean; paused: boolean };

export function describeWorkforceControl(state?: Control | null) {
  if (!state || typeof state.paused !== "boolean" ||
      typeof state.autopilot !== "boolean" ||
      !["auto", "semi", "manual"].includes(state.mode)) {
    return { warning: false, text: "Control settings are unavailable. Don't assume outreach is paused or requires approval." };
  }
  if (state.paused) {
    return { warning: true, text: "Emergency Stop is on. This does not confirm that earlier sends were canceled." };
  }
  if (state.mode === "auto") {
    return { warning: true, text: "Full auto mode is on. Eligible outreach can send without individual approval." };
  }
  if (state.autopilot) {
    return { warning: true, text: "Outreach Autopilot is on. Eligible outreach can send without individual approval, even outside full auto mode." };
  }
  return { warning: false, text: "Full auto and Outreach Autopilot are off. These settings are not a delivery record." };
}
