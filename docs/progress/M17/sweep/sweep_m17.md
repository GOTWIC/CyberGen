# citygen sweep

9 of 10 builds pass (90%)

| spec | pass | builds |
|---|---|---|
| archipelago_free_port | 1 | 1 |
| delta_megacity | 1 | 1 |
| nexus_city | 1 | 1 |
| peninsula_city | 1 | 1 |
| test_delta | 1 | 1 |
| test_minimal | 0 | 1 |
| test_pinned | 1 | 1 |
| test_small | 1 | 1 |
| vesper_bay | 1 | 1 |
| vesper_bay_pinned | 1 | 1 |

| failing check | builds |
|---|---|
| placement | 1 |

| spec | seed | result | failing checks (first failure) | retries | s |
|---|---|---|---|---|---|
| archipelago_free_port | 3301 | pass |  | hv0 rv0 | 73.1 |
| delta_megacity | 4412 | pass |  | hv12 rv3 | 166.1 |
| nexus_city | 1207 | pass |  | hv11 rv0 | 163.9 |
| peninsula_city | 9081 | pass |  | hv0 rv0 city x1 (1) salt 1 | 117.0 |
| test_delta | 12 | pass |  | hv18 rv3 | 131.3 |
| test_minimal | 42 | fail | placement (1): 'Core' is not at edge 'center' | hv11 rv0 city x8 (1,1,1,1,1,1,1,3) | 281.1 |
| test_pinned | 17 | pass |  | hv0 rv0 | 75.2 |
| test_small | 7 | pass |  | hv1 rv0 | 47.6 |
| vesper_bay | 2077 | pass |  | hv18 rv0 | 134.1 |
| vesper_bay_pinned | 2078 | pass |  | hv4 rv0 city x1 (2) salt 1 | 223.5 |
