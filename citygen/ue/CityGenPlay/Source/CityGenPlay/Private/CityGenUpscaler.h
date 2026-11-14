// The upscaler the developer menu picks (dlss_lamps_flicker): native, TSR at 67%, or NVIDIA
// DLSS Super Resolution at its quality, balanced and performance modes, and DLSS Frame
// Generation on or off. DLSS is NVIDIA's plugin, which `citygen unreal --dlss DIR` copies into
// the project; CityGenPlay does not link it: it drives its console variables and calls its
// Blueprint libraries (UDLSSLibrary, UStreamlineLibraryDLSSG, UStreamlineLibraryReflex) by
// reflection, so the play features build and run the same in a project without it.

#pragma once

#include "CoreMinimal.h"

namespace CityGenUpscaler
{
	/** The modes in the menu's order (Default: the engine's own, as the project starts). */
	enum EMode : int32 { Default = -1, Native = 0, Tsr = 1, DlssQuality = 2, DlssBalanced = 3,
		DlssPerformance = 4, Count = 5 };

	/** The modes' row labels and their `upscaler=` names. */
	const TCHAR* Label(int32 Mode);
	const TCHAR* Name(int32 Mode);
	int32 FromName(const FString& Name);

	/** The DLSS plugin is in the game (its console variable r.NGX.DLSS.Enable exists). */
	bool HasDLSS();
	/** ... and DLSS Super Resolution runs on this GPU and driver (UDLSSLibrary). */
	bool DLSSSupported();
	/** DLSS Frame Generation's plugin is in the game (r.Streamline.DLSSG.Enable exists). */
	bool HasFrameGen();
	/** ... and it runs here (UStreamlineLibraryDLSSG: an RTX 40 or newer, DX12, hardware GPU
	 *  scheduling on). */
	bool FrameGenSupported();

	/** The screen percentage a mode renders at for an output size (DLSS's own optimum where
	 *  the plugin answers; 100 native, 67 TSR). */
	float Percent(int32 Mode, const FIntPoint& Output);
	/** Set a mode: DLSS on or off and the screen percentage; false where DLSS is asked and
	 *  not supported (nothing changed). */
	bool Apply(int32 Mode, const FIntPoint& Output);
	/** The mode the console variables show now (Default until one was set). */
	int32 Current();

	/** Frame Generation on (2x) or off; false where it is not supported. */
	bool SetFrameGen(bool bOn);
	bool FrameGenOn();
	/** The frames shown per second with Frame Generation and how many it presents per rendered
	 *  frame (UStreamlineLibraryDLSSG::GetDLSSGFrameTiming); false without it. */
	bool FrameGenTiming(float& Hz, int32& Presented);
	/** Reflex's game to render latency (ms), -1 without it. */
	float LatencyMs();

	/** One JSON object of the above, for CityGen.Status and the benchmark. */
	FString StatusJson(const FIntPoint& Output);
}
