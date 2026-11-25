# JOYSTICK Observatory

This repository contains the JOYSTICK/JSI observatory generated from
Freebielife/TON-Observatory-Template 1.3.0 at
65780137fa12eda7500f48d29c5b261411305274. It is a configured site, not the
shared factory. Keep token settings in project.json. Do not modify other sites.

- Verify token, pool, decimals and sources before changing collection.
- Never replace verified data with empty data on a network/decoding failure.
- DeDust trades use confirmed pool external swap logs (0x9c610de3).
  Verify emitting account, native/JSI asset pair, positive amounts and sender.
- Keep index.html self-contained; only data refresh and wallet lookup need network.
- Run Python tests, Node tests, build.py and verify.py before publishing.
- Check mobile/desktop layout, RU/EN, chart, filters, links, top 10/20 and overflow.
- Preserve concurrent commits. Never force push or overwrite conflicts.
- Report source publication, TON Storage deployment and scheduled runs separately.
- The update.yml schedule is a repository-local fallback. Do not overwrite a shared
  Cloudflare runner or its registry without inspecting its current configuration.
