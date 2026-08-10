async function load() {
  const local = await chrome.storage.local.get({
    apiBase: "http://127.0.0.1:8000",
    lastDiscoveredId: "",
  });
  const sync = await chrome.storage.sync.get({
    apiBase: "http://127.0.0.1:8000",
    lastDiscoveredId: "",
  });
  const data = local.apiBase ? local : sync;
  document.getElementById("apiBase").value = data.apiBase;
  document.getElementById("lastDiscoveredId").value = data.lastDiscoveredId || "";
}

document.getElementById("save").onclick = async () => {
  const payload = {
    apiBase: document.getElementById("apiBase").value.trim() || "http://127.0.0.1:8000",
    lastDiscoveredId: document.getElementById("lastDiscoveredId").value.trim(),
    token: "",
  };
  await chrome.storage.local.set(payload);
  await chrome.storage.sync.set(payload);
  document.getElementById("status").textContent = "Saved.";
};

load();
