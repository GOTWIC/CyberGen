# AG18 step H: hero vehicles parked in Vesper Bay

Vesper Bay built from main with every stage 2 part, then AG18's parked vehicles stage
(`assetgen vehicles`, also part of `assetgen build`), the textured Blender preview, and the
whole city imported into a throwaway Unreal Engine 5.8 project of its own on the M4 Mac,
checked, and shot by day and night.

```bash
.venv/bin/python -m citygen build cities/vesper_bay/city_spec.json out/vb --blockout
.venv/bin/python -m assetgen build out/vb --spec cities/vesper_bay/asset_spec.json
.venv/bin/python -m assetgen materials preview out/vb --night --eye X Y Z --target X Y Z
.venv/bin/python -m citygen unreal out/vb ~/UnrealScratch/CityParked/CityParked.uproject \
    --new-project --check --check-vehicles --shots out/vb/shots --view pday_curb ... night_curb ...
```

## What was placed

TABLE

## Shots

SHOTS

## What the engine showed

ENGINE
