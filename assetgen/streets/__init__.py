"""AG7, street elements (scope 5.3 and 14.8): every street element of a city as a generated
mesh, written per 256 m tile and keyed by citygen ids.

Road surfaces with lane markings, patches, manholes and drains; crosswalks with tactile
paving; sidewalks and curbs in district paving families with tree pits and dropped curbs;
junctions and their sidewalk corners; medians; bridges by kind; decks, ramps, viaducts and
interchanges with parapets, joints, lights, columns and pier caps; tunnels, portals and
approach trenches; quays and canal walls; transit guideways, sky tubes (non-Nanite, with LOD
chains), columns, pylons and station structures; megasite elements. All on M13's grade lines
where a city has terrain (ground 0 where it has none).

`assetgen streets BUILD [--spec S]` (`build.build`) writes `BUILD/assets/streets/`, the
Unreal contribution and the report. Pure Python on integer millimeters, like the rest of
assetgen: the same bytes on every machine and for any worker count.
"""

from .build import STREETS_VERSION  # noqa: F401
