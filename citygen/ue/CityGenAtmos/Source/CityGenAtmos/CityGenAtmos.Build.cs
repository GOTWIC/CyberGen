// atmosgen's runtime (docs/atmosgen_scope.md, docs/unreal_export.md "From AT0"): copied into a
// project and built by `citygen unreal` beside CityGenPlay.

using UnrealBuildTool;

public class CityGenAtmos : ModuleRules
{
	public CityGenAtmos(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		// the plan as JSON
		PrivateDependencyModuleNames.AddRange(new string[] { "Json" });
	}
}
