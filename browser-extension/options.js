async function load() {
  const data = await chrome.storage.sync.get({
    apiBase: "http://127.0.0.1:8000",
    token: "",
    email: "operator@clipops.local",
    lastDiscoveredId: "",
  });
  document.getElementById("apiBase").value = data.apiBase;
  document.getElementById("token").value = data.token;
  document.getElementById("email").value = data.email;
  document.getElementById("lastDiscoveredId").value = data.lastDiscoveredId;
}

document.getElementById("save").onclick = async () => {
  await chrome.storage.sync.set({
    apiBase: document.getElementById("apiBase").value.trim(),
    token: document.getElementById("token").value.trim(),
    email: document.getElementById("email").value.trim(),
    lastDiscoveredId: document.getElementById("lastDiscoveredId").value.trim(),
  });
  document.getElementById("status").textContent = "Saved.";
};

document.getElementById("login").onclick = async () => {
  const apiBase = document.getElementById("apiBase").value.trim();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const status = document.getElementById("status");
  try {
    const res = await fetch(`${apiBase}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    document.getElementById("token").value = data.access_token;
    await chrome.storage.sync.set({
      apiBase,
      email,
      token: data.access_token,
      lastDiscoveredId: document.getElementById("lastDiscoveredId").value.trim(),
    });
    status.textContent = "Logged in and saved token.";
  } catch (e) {
    status.textContent = String(e);
  }
};

load();
