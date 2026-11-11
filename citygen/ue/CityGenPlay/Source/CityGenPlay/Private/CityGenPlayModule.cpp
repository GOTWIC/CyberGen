// The module and its console commands (also what `citygen unreal --check` drives):
// CityGen.Map, CityGen.FreeCam, CityGen.Menu, CityGen.Night [0|1] (toggling without an
// argument), CityGen.Teleport X Y (citygen meters) and CityGen.Status. At game start (not in
// the editor) it also puts the game window at the monitor's native resolution.

#include "CityGenPlayActor.h"
#include "CoreGlobals.h"
#include "Engine/Engine.h"
#include "GameFramework/GameUserSettings.h"
#include "GenericPlatform/GenericApplication.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreDelegates.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenPlayModule, Log, All);

namespace
{
	/** Whether the player's saved settings (Saved/Config/<platform>/GameUserSettings.ini, as
	 *  the game found it at start) chose a resolution. The engine writes that file only when
	 *  a setting is applied and saved, never on its own. */
	bool SavedResolution()
	{
		FString Text;
		return FFileHelper::LoadFileToString(Text, *GGameUserSettingsIni) &&
			Text.Contains(TEXT("ResolutionSizeX="));
	}

	/** The command line sets the window (the benchmark's -windowed -ResX -ResY). */
	bool CommandLineWindow()
	{
		const TCHAR* Cmd = FCommandLine::Get();
		FString V;
		return FParse::Value(Cmd, TEXT("ResX="), V) || FParse::Value(Cmd, TEXT("ResY="), V) ||
			FParse::Param(Cmd, TEXT("windowed")) || FParse::Param(Cmd, TEXT("fullscreen")) ||
			FParse::Value(Cmd, TEXT("CityGenBench="), V);
	}

	/** The packaged game (Swagnik, after AT1): a fresh game with no saved settings picks its
	 *  window before it is made DPI-aware, so on a 1440p screen at 125% it opened at
	 *  2048 x 1152. Once the engine is up (DPI-aware since PreInit), windowed fullscreen at
	 *  the primary monitor's native resolution, unless the player's saved settings or the
	 *  command line chose a window. Nothing is saved: the next start does the same. Unreal's
	 *  automatic screen percentage is left as it is. */
	void NativeResolution(bool bSaved)
	{
		UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
		if (GIsEditor || !S || bSaved || CommandLineWindow())
		{
			return;
		}
		FDisplayMetrics M;
		FDisplayMetrics::RebuildDisplayMetrics(M);
		FIntPoint Native(M.PrimaryDisplayWidth, M.PrimaryDisplayHeight);
		for (const FMonitorInfo& Info : M.MonitorInfo)
		{
			if (Info.bIsPrimary && Info.NativeWidth > 0 && Info.NativeHeight > 0)
			{
				Native = FIntPoint(Info.NativeWidth, Info.NativeHeight);
			}
		}
		if (Native.X <= 0 || Native.Y <= 0)
		{
			return;
		}
		const FIntPoint Was = S->GetScreenResolution();
		S->SetScreenResolution(Native);
		S->SetFullscreenMode(EWindowMode::WindowedFullscreen);
		S->ApplyResolutionSettings(true);
		UE_LOG(LogCityGenPlayModule, Display, TEXT("CityGen play: window %dx%d -> %dx%d windowed fullscreen (the monitor's native resolution)"),
			Was.X, Was.Y, Native.X, Native.Y);
	}
}

class FCityGenPlayModule : public FDefaultModuleImpl
{
public:
	virtual void StartupModule() override
	{
		if (GIsEditor || IsRunningCommandlet() || !FApp::CanEverRender())
		{
			return;
		}
		const bool bSaved = SavedResolution();
		Handle = FCoreDelegates::OnFEngineLoopInitComplete.AddLambda([bSaved]() { NativeResolution(bSaved); });
	}

	virtual void ShutdownModule() override
	{
		FCoreDelegates::OnFEngineLoopInitComplete.Remove(Handle);
	}

private:
	FDelegateHandle Handle;
};

IMPLEMENT_MODULE(FCityGenPlayModule, CityGenPlay)

namespace
{
	ACityGenPlay* PlayIn(UWorld* World)
	{
		ACityGenPlay* P = ACityGenPlay::Find(World);
		if (!P)
		{
			UE_LOG(LogTemp, Warning, TEXT("CityGen: no CityGenPlay actor playing in this world"));
		}
		return P;
	}

	bool Flag(const TArray<FString>& Args, bool bNow)
	{
		return Args.Num() ? FCString::Atoi(*Args[0]) != 0 : !bNow;
	}

	FAutoConsoleCommandWithWorldAndArgs MapCommand(TEXT("CityGen.Map"),
		TEXT("CityGen.Map [0|1]: open or close the map (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetMapOpen(Flag(Args, P->IsMapOpen())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs FreeCamCommand(TEXT("CityGen.FreeCam"),
		TEXT("CityGen.FreeCam [0|1]: the free camera on or off (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetFreeCam(Flag(Args, P->IsFreeCam())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs MenuCommand(TEXT("CityGen.Menu"),
		TEXT("CityGen.Menu [0|1]: open or close the developer menu (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetDevMenuOpen(Flag(Args, P->IsDevMenuOpen())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs NightCommand(TEXT("CityGen.Night"),
		TEXT("CityGen.Night [0|1]: night or day (toggles without an argument)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World)) { P->SetNight(Flag(Args, P->IsNight())); }
		}));

	FAutoConsoleCommandWithWorldAndArgs TeleportCommand(TEXT("CityGen.Teleport"),
		TEXT("CityGen.Teleport X Y: teleport to citygen's (x, y) in meters"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			ACityGenPlay* P = PlayIn(World);
			if (P && Args.Num() >= 2)
			{
				P->TeleportPlayerToCitygen(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs StatusCommand(TEXT("CityGen.Status"),
		TEXT("CityGen.Status: log the play features' state as one JSON line"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ACityGenPlay* P = PlayIn(World))
			{
				UE_LOG(LogTemp, Display, TEXT("CITYGEN_PLAY_STATUS %s"), *P->GetStatus());
			}
		}));
}
