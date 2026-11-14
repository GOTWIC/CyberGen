// The developer menu's upscaler (CityGenUpscaler.h): DLSS through its console variables and,
// by reflection, its Blueprint libraries; nothing here links NVIDIA's plugin.

#include "CityGenUpscaler.h"

#include "HAL/IConsoleManager.h"
#include "UObject/Class.h"
#include "UObject/UnrealType.h"
#include "UObject/UObjectGlobals.h"

namespace
{
	const TCHAR* DlssLib = TEXT("/Script/DLSSBlueprint.DLSSLibrary");
	const TCHAR* FgLib = TEXT("/Script/StreamlineDLSSGBlueprint.StreamlineLibraryDLSSG");
	const TCHAR* ReflexLib = TEXT("/Script/StreamlineReflexBlueprint.StreamlineLibraryReflex");
	// UDLSSLibrary's UDLSSMode: Off, Auto, DLAA, UltraQuality, Quality, Balanced, Performance
	constexpr uint8 DlssModeOf[] = {0, 0, 4, 5, 6};
	// the modes' screen percentages where the plugin does not answer (DLSS's published ratios)
	constexpr float Fallback[] = {100.f, 67.f, 66.667f, 58.f, 50.f};
	int32 GMode = CityGenUpscaler::Default;

	IConsoleVariable* Var(const TCHAR* Name)
	{
		return IConsoleManager::Get().FindConsoleVariable(Name);
	}

	/** A static UFUNCTION of a Blueprint library called by name: `In` fills its parameters,
	 *  `Out` reads them; false when the class or function is not there. */
	bool Call(const TCHAR* ClassPath, const TCHAR* Fn, TFunctionRef<void(UFunction*, uint8*)> In,
		TFunctionRef<void(UFunction*, uint8*)> Out)
	{
		UClass* C = FindObject<UClass>(nullptr, ClassPath);
		UFunction* F = C ? C->FindFunctionByName(FName(Fn)) : nullptr;
		if (!F)
		{
			return false;
		}
		TArray<uint8> Buf;
		Buf.SetNumZeroed(FMath::Max<int32>(F->ParmsSize, 1));
		for (TFieldIterator<FProperty> It(F); It && It->HasAnyPropertyFlags(CPF_Parm); ++It)
		{
			It->InitializeValue_InContainer(Buf.GetData());
		}
		In(F, Buf.GetData());
		C->GetDefaultObject()->ProcessEvent(F, Buf.GetData());
		Out(F, Buf.GetData());
		for (TFieldIterator<FProperty> It(F); It && It->HasAnyPropertyFlags(CPF_Parm); ++It)
		{
			It->DestroyValue_InContainer(Buf.GetData());
		}
		return true;
	}

	bool CallBool(const TCHAR* ClassPath, const TCHAR* Fn)
	{
		bool bRet = false;
		Call(ClassPath, Fn, [](UFunction*, uint8*) {}, [&bRet](UFunction* F, uint8* B)
		{
			if (const FBoolProperty* R = CastField<FBoolProperty>(F->GetReturnProperty()))
			{
				bRet = R->GetPropertyValue_InContainer(B);
			}
		});
		return bRet;
	}

	void SetEnum(UFunction* F, uint8* B, const TCHAR* Name, int64 V)
	{
		FProperty* P = F->FindPropertyByName(FName(Name));
		if (const FEnumProperty* E = CastField<FEnumProperty>(P))
		{
			E->GetUnderlyingProperty()->SetIntPropertyValue(E->ContainerPtrToValuePtr<void>(B), V);
		}
		else if (const FByteProperty* Y = CastField<FByteProperty>(P))
		{
			Y->SetPropertyValue_InContainer(B, uint8(V));
		}
	}

	float GetFloat(UFunction* F, uint8* B, const TCHAR* Name)
	{
		FProperty* P = Name ? F->FindPropertyByName(FName(Name)) : F->GetReturnProperty();
		if (const FFloatProperty* X = CastField<FFloatProperty>(P))
		{
			return X->GetPropertyValue_InContainer(B);
		}
		if (const FDoubleProperty* D = CastField<FDoubleProperty>(P))
		{
			return float(D->GetPropertyValue_InContainer(B));
		}
		return -1.f;
	}
}

namespace CityGenUpscaler
{
	const TCHAR* Label(int32 Mode)
	{
		switch (Mode)
		{
		case Native: return TEXT("Native");
		case Tsr: return TEXT("TSR 67%");
		case DlssQuality: return TEXT("DLSS Quality");
		case DlssBalanced: return TEXT("DLSS Balanced");
		case DlssPerformance: return TEXT("DLSS Perf.");
		default: return TEXT("Default");
		}
	}

	const TCHAR* Name(int32 Mode)
	{
		switch (Mode)
		{
		case Native: return TEXT("native");
		case Tsr: return TEXT("tsr");
		case DlssQuality: return TEXT("dlss_quality");
		case DlssBalanced: return TEXT("dlss_balanced");
		case DlssPerformance: return TEXT("dlss_performance");
		default: return TEXT("default");
		}
	}

	int32 FromName(const FString& N)
	{
		for (int32 M = 0; M < Count; ++M)
		{
			if (N.Equals(Name(M), ESearchCase::IgnoreCase))
			{
				return M;
			}
		}
		return Default;
	}

	bool HasDLSS()
	{
		return Var(TEXT("r.NGX.DLSS.Enable")) != nullptr;
	}

	bool DLSSSupported()
	{
		return HasDLSS() && CallBool(DlssLib, TEXT("IsDLSSSupported"));
	}

	bool HasFrameGen()
	{
		return Var(TEXT("r.Streamline.DLSSG.Enable")) != nullptr;
	}

	bool FrameGenSupported()
	{
		return HasFrameGen() && CallBool(FgLib, TEXT("IsDLSSGSupported"));
	}

	float Percent(int32 Mode, const FIntPoint& Output)
	{
		if (Mode < Native || Mode >= Count)
		{
			return 100.f;
		}
		float Pct = Fallback[Mode];
		if (Mode >= DlssQuality && HasDLSS())
		{
			bool bOk = false;
			float Opt = 0.f;
			Call(DlssLib, TEXT("GetDLSSModeInformation"), [Mode, &Output](UFunction* F, uint8* B)
			{
				SetEnum(F, B, TEXT("DLSSMode"), DlssModeOf[Mode]);
				if (const FStructProperty* S = CastField<FStructProperty>(F->FindPropertyByName(TEXT("ScreenResolution"))))
				{
					*S->ContainerPtrToValuePtr<FVector2D>(B) = FVector2D(Output.X, Output.Y);
				}
			}, [&bOk, &Opt](UFunction* F, uint8* B)
			{
				if (const FBoolProperty* S = CastField<FBoolProperty>(F->FindPropertyByName(TEXT("bIsSupported"))))
				{
					bOk = S->GetPropertyValue_InContainer(B);
				}
				Opt = GetFloat(F, B, TEXT("OptimalScreenPercentage"));
			});
			if (bOk && Opt > 1.f)
			{
				Pct = Opt;
			}
		}
		return Pct;
	}

	bool Apply(int32 Mode, const FIntPoint& Output)
	{
		const bool bDlss = Mode >= DlssQuality && Mode < Count;
		if (bDlss && !DLSSSupported())
		{
			return false;
		}
		if (IConsoleVariable* E = Var(TEXT("r.NGX.DLSS.Enable")))
		{
			E->Set(bDlss ? 1 : 0, ECVF_SetByConsole);
		}
		if (Mode == Default)
		{
			// (back to the engine's own: its automatic screen percentage)
			if (IConsoleVariable* SP = Var(TEXT("r.ScreenPercentage")))
			{
				SP->Set(0.f, ECVF_SetByConsole);
			}
			GMode = Default;
			return true;
		}
		// (TSR is the engine's anti-aliasing at every mode: DLSS takes its place when on)
		if (IConsoleVariable* AA = Var(TEXT("r.AntiAliasingMethod")))
		{
			AA->Set(4, ECVF_SetByConsole);
		}
		if (IConsoleVariable* SP = Var(TEXT("r.ScreenPercentage")))
		{
			SP->Set(Percent(Mode, Output), ECVF_SetByConsole);
		}
		GMode = Mode;
		return true;
	}

	int32 Current()
	{
		const IConsoleVariable* E = Var(TEXT("r.NGX.DLSS.Enable"));
		const IConsoleVariable* SP = Var(TEXT("r.ScreenPercentage"));
		const float Pct = SP ? SP->GetFloat() : 100.f;
		if (E && E->GetInt() != 0)
		{
			return Pct >= 62.f ? DlssQuality : (Pct >= 54.f ? DlssBalanced : DlssPerformance);
		}
		if (GMode == Native || GMode == Tsr)
		{
			return Pct >= 99.f ? Native : Tsr;
		}
		return GMode >= DlssQuality ? (Pct >= 99.f ? Native : Tsr) : Default;
	}

	bool SetFrameGen(bool bOn)
	{
		IConsoleVariable* V = Var(TEXT("r.Streamline.DLSSG.Enable"));
		if (!V || (bOn && !FrameGenSupported()))
		{
			return false;
		}
		V->Set(bOn ? 1 : 0, ECVF_SetByConsole);
		return true;
	}

	bool FrameGenOn()
	{
		const IConsoleVariable* V = Var(TEXT("r.Streamline.DLSSG.Enable"));
		return V && V->GetInt() != 0;
	}

	bool FrameGenTiming(float& Hz, int32& Presented)
	{
		Hz = -1.f;
		Presented = 0;
		return Call(FgLib, TEXT("GetDLSSGFrameTiming"), [](UFunction*, uint8*) {}, [&Hz, &Presented](UFunction* F, uint8* B)
		{
			Hz = GetFloat(F, B, TEXT("FrameRateInHertz"));
			if (const FIntProperty* I = CastField<FIntProperty>(F->FindPropertyByName(TEXT("FramesPresented"))))
			{
				Presented = I->GetPropertyValue_InContainer(B);
			}
		});
	}

	float LatencyMs()
	{
		float Ms = -1.f;
		Call(ReflexLib, TEXT("GetGameToRenderLatencyInMs"), [](UFunction*, uint8*) {}, [&Ms](UFunction* F, uint8* B)
		{
			Ms = GetFloat(F, B, nullptr);
		});
		return Ms;
	}

	FString StatusJson(const FIntPoint& Output)
	{
		float Hz = -1.f;
		int32 Presented = 0;
		const bool bTiming = FrameGenTiming(Hz, Presented);
		const IConsoleVariable* SP = Var(TEXT("r.ScreenPercentage"));
		const int32 M = Current();
		return FString::Printf(TEXT("{\"mode\": \"%s\", \"screen_percentage\": %.2f, \"dlss\": %s, "
			"\"dlss_supported\": %s, \"framegen\": %s, \"framegen_supported\": %s, \"framegen_on\": %s, "
			"\"framegen_hz\": %.2f, \"framegen_presented\": %d, \"latency_ms\": %.2f}"),
			Name(M), SP ? SP->GetFloat() : -1.f, HasDLSS() ? TEXT("true") : TEXT("false"),
			DLSSSupported() ? TEXT("true") : TEXT("false"), HasFrameGen() ? TEXT("true") : TEXT("false"),
			FrameGenSupported() ? TEXT("true") : TEXT("false"), FrameGenOn() ? TEXT("true") : TEXT("false"),
			bTiming ? Hz : -1.f, Presented, LatencyMs());
	}
}
