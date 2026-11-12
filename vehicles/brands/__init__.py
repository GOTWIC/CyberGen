"""The brands' shared helpers: one module per maker of BRANDS.md, holding what that maker's
cars had each carried a copy of (bars, bolts, stencils, badges, glyphs, the brand wheel).

A car script has already put vehicles/ on sys.path, so it imports them as

    from brands import brakk
    from brands.brakk import tube, bolt, stencil

Each module builds on carkit (import carkit as K) with stdlib, bpy and mathutils only. A
helper that read a car's own globals (its PT table, its tire sizes, its bolt collector)
takes them as arguments; functools.partial binds them once at the top of a car:

    build_wheel = partial(brakk.wheel, R=T_R, w=T_W, rim=T_RIM, out=T_OUT, lugs=N_LUG,
                          text=TIRE_TEXT)

What the kit now does itself is not repeated here: each module's docstring says which kit
helper replaces which old copy.
"""
