#include "SCityGenOverlay.h"

#include "CityGenPlayActor.h"
#include "CoreGlobals.h"
#include "Engine/Texture2D.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "InputCoreTypes.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"

namespace
{
	const FLinearColor Sea(0.015f, 0.035f, 0.07f, 0.92f);
	const FLinearColor Accent(0.35f, 0.85f, 1.0f, 1.0f);
	const FLinearColor Ink(0.88f, 0.93f, 1.0f, 1.0f);
	const FLinearColor Dim(0.62f, 0.7f, 0.8f, 1.0f);
	const FLinearColor Panel(0.02f, 0.03f, 0.06f, 0.86f);
	const FLinearColor PlayerColor(1.0f, 0.82f, 0.25f, 1.0f);
	constexpr float Margin = 20.f;
	constexpr float MiniSize = 240.f;
	constexpr double MinScale = 8.0;        // cm per Slate unit, zoomed in all the way
	enum EMenuRow : int32 { RowNight = 1, RowFreeCam = 2, RowMinimap = 3, RowMessages = 4,
		// atmosgen's weather prototypes, shown when the level has its controller
		RowFog = 5, RowRain = 6, RowWet = 7, RowHour = 8, RowHourDown = 9, RowHourUp = 10,
		// AT3: the time-of-day slider under the time row (its own drag, not a click row)
		RowTimeBar = 11,
		// AT5: the weather row (its states; a click the next) and its arrows
		RowWeather = 12, RowWeatherDown = 13, RowWeatherUp = 14 };

	/** A row's name for ACityGenPlay::ClickMenuRow (the console's CityGen.MenuRow). */
	const TCHAR* RowName(int32 Row)
	{
		switch (Row)
		{
		case RowNight: return TEXT("night");
		case RowFreeCam: return TEXT("freecam");
		case RowMinimap: return TEXT("minimap");
		case RowMessages: return TEXT("messages");
		case RowFog: return TEXT("fog");
		case RowRain: return TEXT("rain");
		case RowWet: return TEXT("wet");
		case RowHour: return TEXT("night");     // (AT3: the time row itself swaps day and night)
		case RowHourDown: return TEXT("hour-");
		case RowWeather: return TEXT("weather+");
		case RowWeatherUp: return TEXT("weather+");
		case RowWeatherDown: return TEXT("weather-");
		default: return TEXT("hour+");    // the hour row and its > arrow
		}
	}

	/** The engine's on-screen messages (a big city's "texture streaming pool ... exhausted"
	 *  among them, drawn over the minimap): shown or not, the switch the console's
	 *  DisableAllScreenMessages and EnableAllScreenMessages set. */
	bool EngineMessages()
	{
		return GAreScreenMessagesEnabled;
	}

	FVector2f F(const FVector2D& V) { return FVector2f(float(V.X), float(V.Y)); }
}

void SCityGenOverlay::Construct(const FArguments& InArgs)
{
	Play = InArgs._Play;
	White = FCoreStyle::Get().GetBrush("WhiteBrush");
	MapBrush.DrawAs = ESlateBrushDrawType::Image;
	MapBrush.Tiling = ESlateBrushTileType::NoTile;
	SetVisibility(TAttribute<EVisibility>::CreateSP(this, &SCityGenOverlay::GetHitVisibility));
}

EVisibility SCityGenOverlay::GetHitVisibility() const
{
	const ACityGenPlay* P = Play.Get();
	return P && (P->IsMapOpen() || P->IsDevMenuOpen()) ? EVisibility::Visible
		: EVisibility::HitTestInvisible;
}

// -- drawing helpers --

void SCityGenOverlay::DrawRect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
	const FVector2D& Min, const FVector2D& Max, const FLinearColor& Color) const
{
	FSlateDrawElement::MakeBox(Out, Layer,
		Geometry.ToPaintGeometry(F(Max - Min), FSlateLayoutTransform(F(Min))), White,
		ESlateDrawEffect::None, Color);
}

void SCityGenOverlay::DrawFrame(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
	const FVector2D& Min, const FVector2D& Max, const FLinearColor& Color, float Width) const
{
	TArray<FVector2f> Pts = {F(Min), FVector2f(float(Max.X), float(Min.Y)), F(Max),
		FVector2f(float(Min.X), float(Max.Y)), F(Min)};
	FSlateDrawElement::MakeLines(Out, Layer, Geometry.ToPaintGeometry(), Pts,
		ESlateDrawEffect::None, Color, true, Width);
}

void SCityGenOverlay::DrawText(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
	const FString& Text, const FVector2D& At, int32 FontSize, const FLinearColor& Color,
	bool bBold, bool bCenter) const
{
	const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(bBold ? "Bold" : "Regular", FontSize);
	const FVector2D Size = FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Text, Font);
	const FVector2D Pos = bCenter ? At - Size * 0.5 : At;
	// a shadow, so the text reads over the map and the city alike
	FSlateDrawElement::MakeText(Out, Layer, Geometry.ToPaintGeometry(F(Size),
		FSlateLayoutTransform(F(Pos + FVector2D(1.0, 1.0)))), Text, Font, ESlateDrawEffect::None,
		FLinearColor(0.f, 0.f, 0.f, 0.85f * Color.A));
	FSlateDrawElement::MakeText(Out, Layer + 1, Geometry.ToPaintGeometry(F(Size),
		FSlateLayoutTransform(F(Pos))), Text, Font, ESlateDrawEffect::None, Color);
}

void SCityGenOverlay::DrawArrow(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
	const FVector2D& At, float YawDegrees, float Size) const
{
	// Unreal's yaw turns from +X (east, right on the map) toward +Y (south, down on it)
	const double A = FMath::DegreesToRadians(double(YawDegrees));
	auto Dir = [A](double Off) { return FVector2D(FMath::Cos(A + Off), FMath::Sin(A + Off)); };
	const double Wing = FMath::DegreesToRadians(140.0);
	for (const double K : {1.0, 0.72, 0.46, 0.22})
	{
		const double S = Size * K;
		TArray<FVector2f> Pts = {F(At + Dir(0.0) * S), F(At + Dir(Wing) * S * 0.8),
			F(At - Dir(0.0) * S * 0.25), F(At + Dir(-Wing) * S * 0.8), F(At + Dir(0.0) * S)};
		FSlateDrawElement::MakeLines(Out, Layer, Geometry.ToPaintGeometry(), Pts,
			ESlateDrawEffect::None, K == 1.0 ? FLinearColor(0.f, 0.f, 0.f, 0.9f) : PlayerColor,
			true, K == 1.0 ? 3.5f : 2.5f);
	}
}

void SCityGenOverlay::DrawMap(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
	const FVector2D& Min, const FVector2D& Max, const FVector2D& ViewCenter, double ViewScale) const
{
	const ACityGenPlay* P = Play.Get();
	DrawRect(Out, Layer, Geometry, Min, Max, Sea);
	if (!P || !P->MapTexture)
	{
		return;
	}
	const FVector2D Half = (Max - Min) * 0.5 * ViewScale;
	const FVector2D W0 = ViewCenter - Half, W1 = ViewCenter + Half;
	const FVector2D TL = P->MapTopLeft, BR = P->MapBottomRight;
	const FVector2D I0(FMath::Max(W0.X, TL.X), FMath::Max(W0.Y, TL.Y));
	const FVector2D I1(FMath::Min(W1.X, BR.X), FMath::Min(W1.Y, BR.Y));
	if (I1.X <= I0.X || I1.Y <= I0.Y || BR.X <= TL.X || BR.Y <= TL.Y)
	{
		return;
	}
	const FVector2D L0 = Min + (I0 - W0) / ViewScale, L1 = Min + (I1 - W0) / ViewScale;
	const FVector2D Span = BR - TL;
	MapBrush.SetResourceObject(P->MapTexture);
	MapBrush.SetImageSize(FVector2D(P->MapTexture->GetSizeX(), P->MapTexture->GetSizeY()));
	MapBrush.SetUVRegion(FBox2d(FVector2d((I0.X - TL.X) / Span.X, (I0.Y - TL.Y) / Span.Y),
		FVector2d((I1.X - TL.X) / Span.X, (I1.Y - TL.Y) / Span.Y)));
	FSlateDrawElement::MakeBox(Out, Layer + 1,
		Geometry.ToPaintGeometry(F(L1 - L0), FSlateLayoutTransform(F(L0))), &MapBrush);
}

// -- the map's view --

FVector2D SCityGenOverlay::ToWorld(const FVector2D& Local) const
{
	return Center + (Local - LastSize * 0.5) * Scale;
}

FVector2D SCityGenOverlay::ToLocal(const FVector2D& World) const
{
	return LastSize * 0.5 + (World - Center) / Scale;
}

void SCityGenOverlay::Fit(const FVector2D& Size) const
{
	const ACityGenPlay* P = Play.Get();
	if (!P || Size.X < 1.0 || Size.Y < 1.0)
	{
		return;
	}
	const FVector2D Span = P->MapBottomRight - P->MapTopLeft;
	// the whole city with a margin, under the header and over the hints
	const double Room = FMath::Max(Size.Y - 120.0, Size.Y * 0.5);
	FitScale = FMath::Max(Span.X / Size.X, Span.Y / Room) * 1.04;
	Center = (P->MapTopLeft + P->MapBottomRight) * 0.5;
	Scale = FitScale;
	bFit = false;
}

// -- painting --

int32 SCityGenOverlay::OnPaint(const FPaintArgs& Args, const FGeometry& Geometry,
	const FSlateRect& CullingRect, FSlateWindowElementList& Out, int32 Layer,
	const FWidgetStyle& Style, bool bParentEnabled) const
{
	const ACityGenPlay* P = Play.Get();
	if (!P)
	{
		return Layer;
	}
	LastSize = Geometry.GetLocalSize();
	if (P->IsMapOpen())
	{
		Layer = PaintMap(Out, Layer, Geometry);
	}
	else if (P->bShowMinimap)
	{
		Layer = PaintMinimap(Out, Layer, Geometry);
	}
	if (P->IsDevMenuOpen())
	{
		Layer = PaintMenu(Out, Layer, Geometry);
	}
	const FString Note = P->IsWaitingForStreaming() ? FString(TEXT("Loading the city around you..."))
		: P->GetToast();
	if (!Note.IsEmpty())
	{
		const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Bold", 15);
		const FVector2D Size = FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Note, Font);
		const FVector2D At(LastSize.X * 0.5, P->IsMapOpen() ? LastSize.Y - 90.0 : 64.0);
		DrawRect(Out, Layer + 1, Geometry, At - Size * 0.5 - FVector2D(14.0, 8.0),
			At + Size * 0.5 + FVector2D(14.0, 8.0), Panel);
		DrawText(Out, Layer + 2, Geometry, Note, At, 15, Ink, true, true);
		Layer += 3;
	}
	return Layer;
}

int32 SCityGenOverlay::PaintMinimap(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry) const
{
	const ACityGenPlay* P = Play.Get();
	const FVector2D Min(Margin, Margin), Max(Margin + MiniSize, Margin + MiniSize);
	const FVector View = P->ViewLocation();
	const double ViewScale = 2.0 * double(P->MinimapRadiusM) * 100.0 / MiniSize;
	DrawMap(Out, Layer, Geometry, Min, Max, FVector2D(View.X, View.Y), ViewScale);
	DrawFrame(Out, Layer + 2, Geometry, Min, Max, FLinearColor(Accent.R, Accent.G, Accent.B, 0.7f), 2.f);
	DrawText(Out, Layer + 2, Geometry, TEXT("N"), FVector2D((Min.X + Max.X) * 0.5, Min.Y + 12.0), 11,
		Ink, true, true);
	DrawArrow(Out, Layer + 4, Geometry, (Min + Max) * 0.5, P->ViewYaw(), 11.f);
	// what the player is in, and the keys
	FString Line = P->City.IsEmpty() ? FString(TEXT("CityGen")) : P->City;
	if (P->GetAtmos())
	{
		// (AT3: the time of day, atmosgen's)
		const float H = P->GetAtmosHour();
		Line += FString::Printf(TEXT("  |  %02d:%02d"), FMath::FloorToInt32(H) % 24,
			FMath::FloorToInt32(FMath::Frac(H) * 60.f));
	}
	else
	{
		Line += P->IsNight() ? TEXT("  |  night") : TEXT("  |  day");
	}
	if (P->IsFreeCam())
	{
		Line += FString::Printf(TEXT("  |  free camera %.0f m/s"), P->GetFreeCamSpeed() / 100.f);
	}
	DrawText(Out, Layer + 2, Geometry, Line, FVector2D(Min.X, Max.Y + 8.0), 11, Ink, true);
	DrawText(Out, Layer + 2, Geometry, TEXT("M map   .  free camera   Tab menu"),
		FVector2D(Min.X, Max.Y + 26.0), 10, Dim);
	return Layer + 6;
}

int32 SCityGenOverlay::PaintMap(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry) const
{
	const ACityGenPlay* P = Play.Get();
	if (bFit)
	{
		Fit(LastSize);
	}
	DrawRect(Out, Layer, Geometry, FVector2D::ZeroVector, LastSize, FLinearColor(0.f, 0.f, 0.f, 0.9f));
	DrawMap(Out, Layer + 1, Geometry, FVector2D::ZeroVector, LastSize, Center, Scale);
	// district names, smaller as the map zooms out
	const int32 LabelSize = Scale > FitScale * 0.6 ? 12 : 15;
	for (int32 i = 0; i < P->LabelNames.Num() && i < P->LabelPoints.Num(); ++i)
	{
		DrawText(Out, Layer + 3, Geometry, P->LabelNames[i].ToUpper(), ToLocal(P->LabelPoints[i]),
			LabelSize, FLinearColor(0.85f, 0.92f, 1.f, 0.8f), true, true);
	}
	const FVector View = P->ViewLocation();
	DrawArrow(Out, Layer + 5, Geometry, ToLocal(FVector2D(View.X, View.Y)), P->ViewYaw(), 14.f);
	DrawText(Out, Layer + 6, Geometry, P->City.IsEmpty() ? FString(TEXT("Map")) : P->City,
		FVector2D(LastSize.X * 0.5, 30.0), 20, Ink, true, true);
	DrawText(Out, Layer + 6, Geometry,
		TEXT("Wheel: zoom    Right drag: pan    Left click: teleport    M or Esc: close"),
		FVector2D(LastSize.X * 0.5, LastSize.Y - 40.0), 12, Dim, false, true);
	if (bHover)
	{
		const FVector2D W = ToWorld(Hover);
		DrawText(Out, Layer + 6, Geometry,
			FString::Printf(TEXT("x %.0f m   y %.0f m"), W.X / 100.0, -W.Y / 100.0),
			FVector2D(LastSize.X - 190.0, LastSize.Y - 46.0), 11, Dim);
	}
	return Layer + 8;
}

int32 SCityGenOverlay::PaintMenu(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry) const
{
	const ACityGenPlay* P = Play.Get();
	constexpr double W = 320.0, RowH = 34.0;
	const FVector2D Min(LastSize.X - W - Margin, Margin);
	struct FRow { int32 Id; FString Label; FString Value; };
	const bool bAtmos = P->GetAtmos() != nullptr;
	const float Hr = bAtmos ? P->GetAtmosHour() : 0.f;
	// (AT3: with atmosgen's controller the time row shows its hour, steps it an hour with its
	// arrows, swaps day and night on a click, and a slider under it sets any hour)
	TArray<FRow> Rows = {
		{bAtmos ? RowHour : RowNight, TEXT("Time of day"), bAtmos
			? FString::Printf(TEXT("%02d:%02d"), FMath::FloorToInt32(Hr) % 24, FMath::FloorToInt32(FMath::Frac(Hr) * 60.f))
			: FString(P->IsNight() ? TEXT("Night") : TEXT("Day"))},
		{RowFreeCam, TEXT("Free camera  ( . )"), P->IsFreeCam() ? TEXT("On") : TEXT("Off")},
		{RowMinimap, TEXT("Minimap"), P->bShowMinimap ? TEXT("On") : TEXT("Off")},
		{RowMessages, TEXT("Engine messages"), EngineMessages() ? TEXT("On") : TEXT("Off")}};
	if (P->GetAtmos())
	{
		// AT5: with a weather, one row of its states (clear, drizzle, rain, fog, smog: the rain,
		// the wet streets, the fog and the clouds together, blended); else AT0's switches
		const FString Weather = P->GetAtmosWeather();
		if (!Weather.IsEmpty())
		{
			Rows.Add({RowWeather, TEXT("Weather"), Weather});
		}
		else
		{
			auto OnOff = [P](const TCHAR* Flag) { return FString(P->GetAtmosFlag(Flag) ? TEXT("On") : TEXT("Off")); };
			Rows.Add({RowFog, TEXT("Fog"), OnOff(TEXT("bFog"))});
			Rows.Add({RowRain, TEXT("Rain"), OnOff(TEXT("bRain"))});
			Rows.Add({RowWet, TEXT("Wet streets"), OnOff(TEXT("bWet"))});
		}
	}
	constexpr double BarH = 30.0;
	const double Extra = bAtmos ? BarH : 0.0;
	const FVector2D Max(Min.X + W, Min.Y + 56.0 + Rows.Num() * RowH + Extra + 34.0);
	DrawRect(Out, Layer, Geometry, Min, Max, Panel);
	DrawFrame(Out, Layer + 1, Geometry, Min, Max, FLinearColor(Accent.R, Accent.G, Accent.B, 0.5f), 1.5f);
	DrawText(Out, Layer + 1, Geometry, TEXT("Developer options"), Min + FVector2D(16.0, 14.0), 15, Ink, true);
	MenuRows.Reset();
	bTimeBar = false;
	for (int32 i = 0; i < Rows.Num(); ++i)
	{
		// (the rows after the time row sit under its slider)
		const double Y0 = Min.Y + 52.0 + i * RowH + (i > 0 ? Extra : 0.0);
		const FVector2D R0(Min.X + 8.0, Y0), R1(Max.X - 8.0, R0.Y + RowH - 4.0);
		const FSlateRect Rect(F(R0), F(R1));
		const bool bHour = Rows[i].Id == RowHour;
		const bool bWeatherRow = Rows[i].Id == RowWeather;
		if (bWeatherRow)
		{
			// AT5: the weather steps back and on: its arrows first, so a click there is theirs
			MenuRows.Add(TPair<FSlateRect, int32>(FSlateRect(F(FVector2D(R1.X - 150.0, R0.Y)),
				F(FVector2D(R1.X - 126.0, R1.Y))), RowWeatherDown));
			MenuRows.Add(TPair<FSlateRect, int32>(FSlateRect(F(FVector2D(R1.X - 26.0, R0.Y)), F(R1)),
				RowWeatherUp));
		}
		if (bHour)
		{
			// the hour steps back and on by an hour: its arrows first, so a click there is theirs
			const FSlateRect Down(F(FVector2D(R1.X - 104.0, R0.Y)), F(FVector2D(R1.X - 80.0, R1.Y)));
			const FSlateRect Up(F(FVector2D(R1.X - 26.0, R0.Y)), F(R1));
			MenuRows.Add(TPair<FSlateRect, int32>(Down, RowHourDown));
			MenuRows.Add(TPair<FSlateRect, int32>(Up, RowHourUp));
		}
		MenuRows.Add(TPair<FSlateRect, int32>(Rect, Rows[i].Id));
		const bool bOver = bHover && Rect.ContainsPoint(F(Hover));
		DrawRect(Out, Layer + 1, Geometry, R0, R1, bOver ? FLinearColor(0.2f, 0.45f, 0.6f, 0.55f)
			: FLinearColor(1.f, 1.f, 1.f, 0.05f));
		DrawText(Out, Layer + 2, Geometry, Rows[i].Label, R0 + FVector2D(10.0, 7.0), 12, Ink);
		if (bWeatherRow)
		{
			// (a state's name, "a > b" while it turns, between its arrows)
			DrawText(Out, Layer + 2, Geometry, TEXT("<"), FVector2D(R1.X - 138.0, R0.Y + 15.0), 12, Accent, true, true);
			DrawText(Out, Layer + 2, Geometry, TEXT(">"), FVector2D(R1.X - 13.0, R0.Y + 15.0), 12, Accent, true, true);
			DrawText(Out, Layer + 2, Geometry, Rows[i].Value, FVector2D(R1.X - 76.0, R0.Y + 15.0), 12, Accent, true, true);
		}
		else
		{
			DrawText(Out, Layer + 2, Geometry, Rows[i].Value, FVector2D(R1.X - 70.0, R0.Y + 7.0), 12, Accent, true);
		}
		if (bHour)
		{
			DrawText(Out, Layer + 2, Geometry, TEXT("<"), FVector2D(R1.X - 92.0, R0.Y + 15.0), 12, Accent, true, true);
			DrawText(Out, Layer + 2, Geometry, TEXT(">"), FVector2D(R1.X - 13.0, R0.Y + 15.0), 12, Accent, true, true);
			// AT3: the slider: 24 hours, night dark blue to day pale, the hour marked
			const FVector2D B0(R0.X + 10.0, R1.Y + 8.0), B1(R1.X - 10.0, R1.Y + BarH - 10.0);
			TimeBar = FSlateRect(F(B0), F(B1));
			bTimeBar = true;
			constexpr int32 Steps = 48;
			for (int32 s = 0; s < Steps; ++s)
			{
				const double X0 = FMath::Lerp(B0.X, B1.X, double(s) / Steps);
				const double X1 = FMath::Lerp(B0.X, B1.X, double(s + 1) / Steps);
				const float Day = FMath::Clamp(0.5f - 0.5f * FMath::Cos(2.f * UE_PI * (float(s) + 0.5f) / float(Steps)), 0.f, 1.f);
				const FLinearColor C = FMath::Lerp(FLinearColor(0.03f, 0.05f, 0.14f, 0.95f),
					FLinearColor(0.55f, 0.72f, 0.9f, 0.95f), Day * Day);
				DrawRect(Out, Layer + 1, Geometry, FVector2D(X0, B0.Y), FVector2D(X1, B1.Y), C);
			}
			for (int32 h = 0; h <= 24; h += 6)
			{
				const double X = FMath::Lerp(B0.X, B1.X, h / 24.0);
				DrawRect(Out, Layer + 2, Geometry, FVector2D(X - 0.5, B1.Y - 4.0), FVector2D(X + 0.5, B1.Y), Dim);
			}
			const double HX = FMath::Lerp(B0.X, B1.X, double(Hr) / 24.0);
			DrawRect(Out, Layer + 3, Geometry, FVector2D(HX - 2.0, B0.Y - 3.0), FVector2D(HX + 2.0, B1.Y + 3.0), Accent);
		}
	}
	DrawText(Out, Layer + 2, Geometry, bAtmos ? TEXT("Click a row to change it, drag the time.  Tab or Esc closes.")
		: TEXT("Click a row to change it.  Tab or Esc closes."),
		FVector2D(Min.X + 16.0, Max.Y - 26.0), 10, Dim);
	return Layer + 4;
}

// -- input (only while the map or the menu is open) --

FReply SCityGenOverlay::OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
	ACityGenPlay* P = Play.Get();
	if (!P)
	{
		return FReply::Unhandled();
	}
	const FKey Key = Event.GetKey();
	if (Key == EKeys::M)
	{
		P->SetMapOpen(!P->IsMapOpen());
	}
	else if (Key == EKeys::Tab)
	{
		P->SetDevMenuOpen(!P->IsDevMenuOpen());
	}
	else if (Key == EKeys::Escape && (P->IsMapOpen() || P->IsDevMenuOpen()))
	{
		P->SetMapOpen(false);
		P->SetDevMenuOpen(false);
	}
	else
	{
		return FReply::Unhandled();
	}
	return FReply::Handled();
}

FReply SCityGenOverlay::OnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event)
{
	ACityGenPlay* P = Play.Get();
	if (!P)
	{
		return FReply::Unhandled();
	}
	const FVector2D Local = Geometry.AbsoluteToLocal(Event.GetScreenSpacePosition());
	Hover = Local;
	bHover = true;
	if (P->IsDevMenuOpen() && Event.GetEffectingButton() == EKeys::LeftMouseButton)
	{
		// AT3: the time slider, dragged
		if (bTimeBar && TimeBar.ExtendBy(FMargin(0.f, 6.f)).ContainsPoint(F(Local)))
		{
			bDragTime = true;
			SetTimeFrom(Local);
			return FReply::Handled().CaptureMouse(SharedThis(this));
		}
		for (const TPair<FSlateRect, int32>& Row : MenuRows)
		{
			if (!Row.Key.ContainsPoint(F(Local)))
			{
				continue;
			}
			P->ClickMenuRow(RowName(Row.Value));
			return FReply::Handled();
		}
	}
	if (P->IsMapOpen())
	{
		if (Event.GetEffectingButton() == EKeys::RightMouseButton)
		{
			bPanning = true;
			PanFrom = Local;
			return FReply::Handled().CaptureMouse(SharedThis(this));
		}
		if (Event.GetEffectingButton() == EKeys::LeftMouseButton)
		{
			const FVector2D W = ToWorld(Local);
			const FVector2D TL = P->MapTopLeft, BR = P->MapBottomRight;
			if (W.X >= TL.X && W.X <= BR.X && W.Y >= TL.Y && W.Y <= BR.Y)
			{
				P->SetMapOpen(false);
				P->TeleportPlayer(FVector(W.X, W.Y, 0.0));
			}
			return FReply::Handled();
		}
	}
	return FReply::Handled();
}

void SCityGenOverlay::SetTimeFrom(const FVector2D& Local)
{
	ACityGenPlay* P = Play.Get();
	const float W = TimeBar.Right - TimeBar.Left;
	if (!P || W <= 1.f)
	{
		return;
	}
	// (to the quarter hour)
	const float H = FMath::Clamp(float(Local.X - TimeBar.Left) / W, 0.f, 1.f) * 24.f;
	P->SetTimeOfDay(FMath::RoundToFloat(H * 4.f) / 4.f);
}

FReply SCityGenOverlay::OnMouseButtonUp(const FGeometry& Geometry, const FPointerEvent& Event)
{
	if (bDragTime && Event.GetEffectingButton() == EKeys::LeftMouseButton)
	{
		bDragTime = false;
		return FReply::Handled().ReleaseMouseCapture();
	}
	if (bPanning && Event.GetEffectingButton() == EKeys::RightMouseButton)
	{
		bPanning = false;
		return FReply::Handled().ReleaseMouseCapture();
	}
	return FReply::Handled();
}

FReply SCityGenOverlay::OnMouseMove(const FGeometry& Geometry, const FPointerEvent& Event)
{
	const FVector2D Local = Geometry.AbsoluteToLocal(Event.GetScreenSpacePosition());
	if (bDragTime)
	{
		SetTimeFrom(Local);
	}
	if (bPanning)
	{
		Center -= (Local - PanFrom) * Scale;
		PanFrom = Local;
	}
	Hover = Local;
	bHover = true;
	return FReply::Handled();
}

FReply SCityGenOverlay::OnMouseWheel(const FGeometry& Geometry, const FPointerEvent& Event)
{
	const ACityGenPlay* P = Play.Get();
	if (!P || !P->IsMapOpen())
	{
		return FReply::Handled();
	}
	// zoom about the point under the cursor
	const FVector2D Local = Geometry.AbsoluteToLocal(Event.GetScreenSpacePosition());
	const FVector2D Under = ToWorld(Local);
	const double Step = Event.GetWheelDelta() > 0.f ? 0.8 : 1.25;
	Scale = FMath::Clamp(Scale * Step, MinScale, FitScale * 2.0);
	Center = Under - (Local - LastSize * 0.5) * Scale;
	return FReply::Handled();
}

FCursorReply SCityGenOverlay::OnCursorQuery(const FGeometry& Geometry, const FPointerEvent& Event) const
{
	const ACityGenPlay* P = Play.Get();
	if (bPanning)
	{
		return FCursorReply::Cursor(EMouseCursor::GrabHandClosed);
	}
	if (P && P->IsMapOpen())
	{
		return FCursorReply::Cursor(EMouseCursor::Crosshairs);
	}
	return FCursorReply::Cursor(EMouseCursor::Default);
}
