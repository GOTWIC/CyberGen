# Places on and off at fixed viewpoints (game thread, ms a frame)

Read lifegen's own timers (`CityGenLife_*`): the engine's timers differ by what streamed in
each 30 s window, and the last window (places off, Midtown) also holds the game's exit
(`FEngineLoop::Exit`, the purge), which its region ran into.

## d02_wk_e1715n1224

Frames 2318 (places on) and 2051 (off); the game thread's frame 13.71 ms against 15.54 ms.

| timer | on incl | off incl | on excl | off excl | diff incl |
|---|---|---|---|---|---|
| CityGenLifeDriveProcessor_0 | 0.236 | 0.192 | 0.002 | 0.001 | +0.044 |
| CityGenLifeGround | 0.188 | 0.126 | 0.168 | 0.112 | +0.062 |
| CityGenLifeWalkProcessor_0 | 0.191 | 0.150 | 0.003 | 0.003 | +0.041 |
| CityGenLife_DoorSpawns | 0.000 | 0.000 | 0.000 | 0.000 | -0.000 |
| CityGenLife_ExecuteCity | 0.187 | 0.147 | 0.187 | 0.147 | +0.040 |
| CityGenLife_ExecuteTraffic | 0.234 | 0.191 | 0.234 | 0.191 | +0.043 |
| CityGenLife_FindGround | 0.416 | 0.309 | 0.216 | 0.175 | +0.107 |
| CityGenLife_FollowAtmos | 0.001 | 0.001 | 0.001 | 0.001 | +0.000 |
| CityGenLife_ThinOut | 0.000 | 0.000 | 0.000 | 0.000 | -0.000 |
| CityGenLife_Tick | 2.003 | 1.530 | 0.089 | 0.070 | +0.473 |
| CityGenLife_UAID_C87F54669DD3981403 | 2.005 | 1.534 | 0.002 | 0.002 | +0.471 |
| CityGenLife_UpdateAirWater | 0.181 | 0.139 | 0.115 | 0.090 | +0.042 |
| CityGenLife_UpdateCarInstances | 0.257 | 0.185 | 0.223 | 0.160 | +0.073 |
| CityGenLife_UpdateInstances | 0.800 | 0.597 | 0.002 | 0.001 | +0.203 |
| CityGenLife_UpdateLive | 0.008 | 0.006 | 0.008 | 0.006 | +0.003 |
| CityGenLife_UpdatePeople | 0.412 | 0.313 | 0.184 | 0.134 | +0.099 |
| CityGenLife_UpdateTraffic | 0.008 | 0.007 | 0.008 | 0.007 | +0.001 |
| CityGenLife_UpdateTransit | 0.055 | 0.042 | 0.038 | 0.030 | +0.012 |
| CityGenLife_UpdateUmbrellas | 0.129 | 0.098 | 0.029 | 0.023 | +0.031 |
| SmartObjectSubsystemRenderingActor | 0.000 | 0.000 | 0.000 | 0.000 | -0.000 |
| FObjectPurge::DestroyObjects | 0.000 | 8.523 | 0.000 | 8.523 | -8.523 |
| ConditionalFinishDestroy | 0.000 | 6.258 | 0.000 | 5.840 | -6.258 |
| ReflexSleep | 4.824 | 8.562 | 4.824 | 8.562 | -3.738 |
| ConditionalBeginDestroy | 0.000 | 1.089 | 0.000 | 0.790 | -1.089 |
| FEngineLoop::Exit | 0.000 | 18.399 | 0.000 | 0.547 | -18.399 |
| FCoreDelegates::OnPreExit | 0.000 | 12.069 | 0.000 | 0.423 | -12.069 |
| Destroy Pending Proxies | 0.000 | 0.365 | 0.000 | 0.365 | -0.365 |
| MeshObject Update | 0.765 | 0.455 | 0.764 | 0.454 | +0.311 |
| STAT_FPendingCleanupObjects_Destruct | 0.000 | 0.296 | 0.000 | 0.296 | -0.296 |
| UStaticMesh::ReleaseResources | 0.000 | 0.289 | 0.000 | 0.260 | -0.289 |
| UnloadModulesAtShutdown | 0.000 | 0.564 | 0.000 | 0.233 | -0.564 |
| Game thread idle time | 0.005 | 0.214 | 0.005 | 0.214 | -0.209 |
| STAT_FLinkerManager_DeleteLinkers | 0.000 | 0.126 | 0.000 | 0.126 | -0.126 |
| CollectUnreachableObjectsTask | 0.000 | 0.113 | 0.000 | 0.113 | -0.113 |
| STAT_UInstancedStaticMeshComponent_BuildRenderData | 0.872 | 0.706 | 0.440 | 0.350 | +0.167 |
| UStaticMesh::GetUsedMaterials | 0.432 | 0.356 | 0.432 | 0.356 | +0.076 |
| UInstancedStaticMeshComponent::BatchUpdateInstancesTransforms | 0.306 | 0.231 | 0.306 | 0.231 | +0.075 |
| AppPreExit | 0.000 | 16.953 | 0.000 | 0.073 | -16.953 |
| InterruptQueue_Process | 0.000 | 0.063 | 0.000 | 0.063 | -0.063 |
| DDC_WaitForQuiescence | 0.000 | 0.056 | 0.000 | 0.056 | -0.056 |
| STAT_TaskGraph_EnqueueFromOtherThread_Trigger | 0.016 | 0.069 | 0.016 | 0.069 | -0.053 |
| UObject::Rename | 0.000 | 0.051 | 0.000 | 0.051 | -0.051 |

## d04_wk_w1574n1277

Frames 2113 (places on) and 1679 (off); the game thread's frame 15.03 ms against 18.93 ms.

| timer | on incl | off incl | on excl | off excl | diff incl |
|---|---|---|---|---|---|
| CityGenLifeDriveProcessor_0 | 0.638 | 0.595 | 0.003 | 0.002 | +0.043 |
| CityGenLifeGround | 0.714 | 0.539 | 0.644 | 0.487 | +0.176 |
| CityGenLifeWalkProcessor_0 | 0.499 | 0.455 | 0.004 | 0.003 | +0.044 |
| CityGenLife_DoorSpawns | 0.000 | 0.000 | 0.000 | 0.000 | -0.000 |
| CityGenLife_ExecuteCity | 0.495 | 0.452 | 0.495 | 0.452 | +0.043 |
| CityGenLife_ExecuteTraffic | 0.635 | 0.593 | 0.635 | 0.593 | +0.043 |
| CityGenLife_FindGround | 0.986 | 0.767 | 0.242 | 0.204 | +0.220 |
| CityGenLife_FollowAtmos | 0.001 | 0.001 | 0.001 | 0.001 | +0.000 |
| CityGenLife_ThinOut | 0.000 | 0.000 | 0.000 | 0.000 | -0.000 |
| CityGenLife_Tick | 3.690 | 3.329 | 0.128 | 0.097 | +0.362 |
| CityGenLife_UAID_C87F54669DD3981403 | 3.692 | 3.330 | 0.002 | 0.002 | +0.362 |
| CityGenLife_UpdateAirWater | 0.180 | 0.168 | 0.115 | 0.107 | +0.012 |
| CityGenLife_UpdateCarInstances | 0.484 | 0.479 | 0.452 | 0.448 | +0.005 |
| CityGenLife_UpdateInstances | 1.142 | 1.150 | 0.002 | 0.002 | -0.009 |
| CityGenLife_UpdateLive | 0.014 | 0.011 | 0.014 | 0.011 | +0.004 |
| CityGenLife_UpdatePeople | 0.522 | 0.537 | 0.231 | 0.234 | -0.015 |
| CityGenLife_UpdateTraffic | 0.014 | 0.009 | 0.014 | 0.009 | +0.004 |
| CityGenLife_UpdateTransit | 0.060 | 0.055 | 0.041 | 0.038 | +0.005 |
| CityGenLife_UpdateUmbrellas | 0.134 | 0.132 | 0.035 | 0.037 | +0.001 |
| ReflexSleep | 0.094 | 3.649 | 0.094 | 3.649 | -3.555 |
| AddPrimitive (GT) | 0.171 | 2.894 | 0.108 | 1.558 | -2.723 |
| UStaticMesh::GetUsedMaterials | 0.557 | 1.744 | 0.557 | 1.744 | -1.187 |
| Game thread idle time | 0.700 | 1.417 | 0.700 | 1.417 | -0.718 |
| PerformReachabilityAnalysisOnObjectsInternal | 0.583 | 0.000 | 0.583 | 0.000 | +0.583 |
| LinkerLoad_CreateLoader | 0.411 | 0.000 | 0.411 | 0.000 | +0.411 |
| ConditionalFinishDestroy | 0.378 | 0.000 | 0.375 | 0.000 | +0.378 |
| ConditionalBeginDestroy | 0.244 | 0.000 | 0.242 | 0.000 | +0.244 |
| PyUtil::CollectGarbage | 0.172 | 0.000 | 0.172 | 0.000 | +0.172 |
| FShaderCompilingManager::PropagateMaterialChangesToPrimitives | 0.000 | 0.164 | 0.000 | 0.120 | -0.164 |
| UObject_Serialize | 0.119 | 0.000 | 0.119 | 0.000 | +0.119 |
| Post Tick Component Update | 3.103 | 6.128 | 0.030 | 0.131 | -3.025 |
| FObjectPurge::DestroyObjects | 0.099 | 0.000 | 0.099 | 0.000 | +0.099 |
| UInstancedStaticMeshComponent::CalcBoundsImpl | 0.528 | 0.442 | 0.528 | 0.442 | +0.086 |
| DeferredRenderUpdates_GameThread | 3.070 | 5.990 | 0.137 | 0.209 | -2.921 |
| STAT_UInstancedStaticMeshComponent_BuildRenderData | 1.030 | 1.379 | 0.532 | 0.602 | -0.348 |
| Recreate | 0.002 | 0.087 | 0.002 | 0.071 | -0.085 |
| UObject::Rename | 0.060 | 0.000 | 0.060 | 0.000 | +0.060 |
| CityGenAtmos_UAID_C87F54669DD38D1303 | 0.765 | 0.612 | 0.194 | 0.140 | +0.153 |
| Plane | 0.355 | 0.299 | 0.233 | 0.181 | +0.056 |
| STAT_FMemory_Trim_GMalloc | 0.052 | 0.000 | 0.052 | 0.000 | +0.052 |
| STAT_FLinkerManager_DeleteLinkers | 0.047 | 0.000 | 0.047 | 0.000 | +0.047 |

