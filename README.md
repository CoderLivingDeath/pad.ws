# pad.ws -  whiteboard as an IDE 🎨



[![Pad.ws Canvas IDE](docs/canvas_ide.png)](https://pad.ws)

[pad.ws](https://pad.ws) is a whiteboard app that acts as a dev environment in your browser

## ✨ Features

* 🎨 **Interactive Whiteboard** - Draw, sketch and visualize your ideas with Excalidraw
* 💻 **Fully fledged IDE** - Access terminals and VS Code directly within the whiteboard
* ☁️ **Browser friendly** - Access your dev env from any device
* 🔄 **Seamless Workflow** - Switch between visual ideation and coding
* 🛠️ **Use your own tools** - Access your VM from your desktop client (VS Code & Cursor supported)

This uses [Excalidraw](https://github.com/excalidraw/excalidraw) for the whiteboard interface while [Coder](https://github.com/coder/coder) powers the cloud development environments.


## Try it online  🌐

Visit [pad.ws](https://pad.ws) for an official managed instance. During this beta, we offer free ubuntu dev environments without any setup

## Self-Hosting 🛠️

For a secure, production-ready deployment, follow the operator runbook at [`docs/deployment.md`](docs/deployment.md). It covers DNS, firewall, secret generation, Keycloak and Coder configuration, the local `*.pad.test` acceptance mode, backup/restore, rollback, security considerations and the curl-based smoke test.

> ⚠️ **Development-only**: the `docker-compose.yml` file in the repository root uses `network_mode: host`, publishes database/cache ports and ships with default/weak credentials. It is intended for local development only and must not be used on a publicly reachable host.

### Development quick start (insecure)

If you only want to run the stack locally for development:

1. Copy the development template and review the values:

   ```bash
   cp .env.template .env
   ```

2. Start the services:

   ```bash
   docker compose up -d
   ```

3. Configure Keycloak and Coder manually using the old localhost ports. See `deploy/keycloak/README.md` and `deploy/coder/README.md` for guidance.

For anything reachable from the internet, use `docker-compose.prod.yml` and `docs/deployment.md` instead.

🚧 *Did you have any issue while following this guide?*

*Please [let us know](https://github.com/pad-ws/pad.ws/issues) so we can improve the onboarding flow*

## 🚀 Project Growth

[![Star History Chart](https://api.star-history.com/svg?repos=pad-ws/pad.ws&type=Date)](https://star-history.com/#pad-ws/pad.ws&Date)
