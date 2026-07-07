import { ref } from "vue";

const prefs = JSON.parse(localStorage.getItem("kf_prefs") || "{}");

/** @type {ReturnType<typeof useAppStore>|null} */
let _instance = null;

/**
 * Singleton app state composable.
 * Returns top-level refs for template auto-unwrap.
 */
export function useAppStore() {
  if (_instance) return _instance;

  const nav = ref(prefs.nav || "chat");
  const apiKey = ref("");
  const chatId = ref("");
  const turnId = ref(0);
  const chatMessages = ref([]);
  const streamDefault = ref(prefs.streamDefault !== false);
  const theme = ref(prefs.theme || "light");
  const connected = ref(false);

  _instance = { nav, apiKey, chatId, turnId, chatMessages, streamDefault, theme, connected };
  return _instance;
}
