# WIP 01: the small test city with stage 2

The small test city (tests/conftest.py SMALL) imported blockout only, then with assetgen's
buildings and streets over it (7435 actors created, 3216 updated, 498 deleted: exactly what
`manifest_changes` names), then again (nothing changed) and checked: 507 of 507 traces
down, 36 of 36 roofs and facades, 248 m walked. Shots at 1600 px.
