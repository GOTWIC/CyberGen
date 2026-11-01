// The play features' screen overlay, drawn by hand (no widget Blueprint): the minimap (top
// left), the map (M: the wheel zooms about the cursor, the right button pans, the left one
// teleports), the developer menu (Tab) and short notices. Hit-testable only while the map or
// the menu is open, so it never takes the game's mouse otherwise.

#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SLeafWidget.h"

class ACityGenPlay;

class SCityGenOverlay : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SCityGenOverlay) {}
		SLATE_ARGUMENT(TWeakObjectPtr<ACityGenPlay>, Play)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** The map was opened: fit the whole city on screen again. */
	void ResetMapView() { bFit = true; bPanning = false; }

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry,
		const FSlateRect& CullingRect, FSlateWindowElementList& Out, int32 Layer,
		const FWidgetStyle& Style, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(64.0, 64.0); }
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event) override;
	virtual FReply OnMouseButtonDown(const FGeometry& Geometry, const FPointerEvent& Event) override;
	virtual FReply OnMouseButtonUp(const FGeometry& Geometry, const FPointerEvent& Event) override;
	virtual FReply OnMouseMove(const FGeometry& Geometry, const FPointerEvent& Event) override;
	virtual FReply OnMouseWheel(const FGeometry& Geometry, const FPointerEvent& Event) override;
	virtual FCursorReply OnCursorQuery(const FGeometry& Geometry, const FPointerEvent& Event) const override;

private:
	EVisibility GetHitVisibility() const;
	/** The map's view: Unreal XY (cm) at a local point of the widget, and back. */
	FVector2D ToWorld(const FVector2D& Local) const;
	FVector2D ToLocal(const FVector2D& World) const;
	void Fit(const FVector2D& Size) const;
	/** The part of the map image inside a rectangle of the widget, drawn there. */
	void DrawMap(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
		const FVector2D& Min, const FVector2D& Max, const FVector2D& Center, double Scale) const;
	void DrawArrow(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
		const FVector2D& At, float YawDegrees, float Size) const;
	void DrawText(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
		const FString& Text, const FVector2D& At, int32 FontSize, const FLinearColor& Color,
		bool bBold = false, bool bCenter = false) const;
	void DrawRect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
		const FVector2D& Min, const FVector2D& Max, const FLinearColor& Color) const;
	void DrawFrame(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry,
		const FVector2D& Min, const FVector2D& Max, const FLinearColor& Color, float Width) const;
	int32 PaintMinimap(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry) const;
	int32 PaintMap(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry) const;
	int32 PaintMenu(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geometry) const;

	TWeakObjectPtr<ACityGenPlay> Play;
	mutable FSlateBrush MapBrush;
	const FSlateBrush* White = nullptr;

	// the map's view: its center (Unreal XY, cm) and scale (cm per Slate unit)
	mutable bool bFit = true;
	mutable FVector2D Center = FVector2D::ZeroVector;
	mutable double Scale = 100.0;
	mutable double FitScale = 100.0;
	mutable FVector2D LastSize = FVector2D(1920.0, 1080.0);
	bool bPanning = false;
	FVector2D PanFrom = FVector2D::ZeroVector;
	FVector2D Hover = FVector2D::ZeroVector;
	bool bHover = false;

	// the menu's rows, where they were drawn (local rectangles), and what each does
	mutable TArray<TPair<FSlateRect, int32>> MenuRows;
};
