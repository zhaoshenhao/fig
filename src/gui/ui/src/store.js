import { reactive } from "vue";

const stored = JSON.parse(localStorage.getItem("kf_prefs") || "{}");

export const store = reactive({
  nav: stored.nav || "chat",
  apiKey: "",
  chatId: "",
  turnId: 0,
  chatMessages: [],
  streamDefault: stored.streamDefault !== false,
  theme: stored.theme || "light",
  connected: false,
  _persist() {
    localStorage.setItem(
      "kf_prefs",
      JSON.stringify({
        nav: this.nav,
        streamDefault: this.streamDefault,
        theme: this.theme,
      })
    );
  },
});
