# Install FareHunter in Claude Desktop

**English** · [Português](claude-desktop.pt-BR.md) · [Español](claude-desktop.es.md)

For **macOS and Windows**. No terminal needed.

## 1. Get Claude Desktop
Download it from https://claude.ai/download and sign in. Your plan must include Claude Code.

## 2. Add the plugin
1. Open **Settings** and, under *Customization*, click **Plugins**.
2. Click **+ Add** (top right) → **Add marketplace**.
3. In the **URL** field type `s0beran0/farehunter`, choose **Use "…"** and click **Sync**.
4. On the **Discover** tab, click **Add** next to **Farehunter**.

## 3. Finish the setup
1. Open the **Code** tab and pick any folder (e.g. `Documents/trips`).
2. Type `/farehunter:setup`.
3. Follow what it says. It checks your computer and shows the exact link or command for the one required tool (**uv**).

That's it. Start with `/farehunter:profile`, then ask for a trip, e.g. `/farehunter:search New York to Lisbon Nov 20, back Nov 27`.

## Update
**Settings → Plugins → + Add → Manage marketplaces**, then sync **farehunter-marketplace**.

---
Using Claude in the terminal instead? See [Install in Claude Code](claude-code.md).
