# Pushing Dispatch_

Multi-model dispatch for AI coding agents. One , many models.

## Quick start

```bash
# 1. Clone and configure
git clone <repository-url>
cd <checkout-directory>
cp dispatch_matrix.toml.example dispatch_matrix.toml
# 2. Check prerequisites
bash bin/check-prereqs.sh
# 3. Configure at least one supported provider using its documented credential mechanism
# 4. Write a brief
cat > /tmp/my-brief.md << 'EOF'
---
title: Fix lint warnings
executor: <configured-executor>
```

## Docs

- [docs/PROVIDERS.md](docs/PROVIDERS.md) — executor roster incl. `grok-build`, `zai-glm` (ZCode), Kimi K3 lanes
- [ops/unsloth-nucbox/README.md](ops/unsloth-nucbox/README.md)
- [INSTALL.md](INSTALL.md)
- [docs/ORCHESTRATING.md](docs/ORCHESTRATING.md)
- [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md)

## License

See [LICENSE](LICENSE).
