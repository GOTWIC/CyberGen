// citygen's play features (docs/unreal_export.md, "Play features"): copied into a project
// and built by `citygen unreal` before the import.

using UnrealBuildTool;

public class CityGenPlay : ModuleRules
{
	public CityGenPlay(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[] { "InputCore", "Slate", "SlateCore" });
	}
}
