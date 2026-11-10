# Brief for a car design session (AG18)

You design ONE vehicle and deliver one multi-view sheet of it. This file is the same for
every car; your own assignment (brand, model, type) comes with your task.

## Read first

1. `vehicles/README.md`: the kit, its API, the workflow and the lessons already learned.
2. `vehicles/BRANDS.md`: your brand's design language and the whole roster, so your car fits
   its brand and looks like no other car on the list.
3. `vehicles/cars/vanta_r.py` and `docs/progress/AG18/vanta_r/sheet.jpg`: a worked example
   and the standard to match or beat.
4. The owner's concept references, outside git:
   `/Users/swag/Projects/CyberGen/reference/car_concepts/view/c01.jpg` to `c14.jpg`. They are
   inspiration for mood and ideas only. They are not ours: never copy any one of them, in
   whole or in a recognisable part. Bring your own proportions, details and ideas.
5. Any car of your brand already in `vehicles/cars/` and its sheet in
   `docs/progress/AG18/`, so the family resemblance is real.

## What to make

- Cyber-futurism. Sharp or smooth as your brand says. Be bold: gaps through the body,
  wheels outside the body, hover gear, canopies, whatever makes it striking and its own.
- A believable machine: people fit (seats, head room, a way in), wheels and tires of
  sensible size with room to steer, or emitters and skids that could carry it; ground
  clearance; lights front and rear; glass you can see a cabin through.
- The brand lives in geometry and texture, never in color. Pick a show color that suits the
  car; do not reuse another car's color if you can see one.
- The level of the Vanta-R sheet or better: clean surfaces, crisp creases where the design
  wants them, real panel gaps, wheels or emitters with detail, lights, glass with a simple
  cabin behind it (seats, dash, wheel), and a layer of small detail (vents, fasteners,
  made-up lettering, markers).
- Not needed: UVs, LODs, rigging, a game-ready mesh, beauty shots. One sheet is the
  deliverable.
- Frame: x forward, y left, z up, meters, origin on the ground under the middle.
- All names and lettering made up. Never a real maker, a real model or any game.

## How to work

- Decide the car on paper first: length, width, height, wheelbase, seating, the three or
  four ideas that make it this car. Then the body's lines and stations in numbers.
- Look at a `--preview` after every change of substance and really look at it: proportions
  and stance first, then surfaces, then details. Check all four views, not only the hero.
- Car-specific helpers go in your own script. Do NOT edit `carkit.py`, `post.py`,
  `blender.sh` or any other shared file: other sessions are working beside you. If the kit
  lacks something, work around it in your script and list it under "Kit wishes".
- When it is good, run `--sheet` once (twice at most) into your car's folder.

## This Mac is shared

- Every Blender run goes through `vehicles/blender.sh` (it queues behind the other
  sessions' runs). Never start Blender any other way, never two runs at once, nothing else
  heavy (no test suites, no city builds).
- Previews at the kit's cheap defaults. No renders larger than the sheet.
- Scratch output (previews, logs) goes outside the repo, in a folder of your own under
  `/tmp` or your scratchpad. PIL and numpy: `/Users/swag/Projects/CyberGen/.venv/bin/python`.

## Deliver

In your worktree, on a branch `claude/ag18-<slug>` (slug: brand and model in lower case,
for example `kestrel_dart`):

- `vehicles/cars/<slug>.py`
- `docs/progress/AG18/<slug>/sheet.jpg` (the one 4K multi-view image)
- `docs/progress/AG18/<slug>/README.md`: a dozen lines: brand, model, type, seats, length,
  width, height, wheelbase or ride height, the design in a few bullets, triangle count,
  the command that builds the sheet, what you would improve, "Kit wishes".

Nothing else in the commit (no .blend, no .glb, no previews). No em dashes anywhere.
Commit message ending with `Co-Authored-By: Claude <noreply@anthropic.com>`, push, and open
a PR with `gh pr create`, title `AG18: <Brand> <Model> (<type>)`, a short body ending with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Do not merge it.

Your final message: the PR number, the car in five lines, its size and triangle count, how
long it took, and your kit wishes.
