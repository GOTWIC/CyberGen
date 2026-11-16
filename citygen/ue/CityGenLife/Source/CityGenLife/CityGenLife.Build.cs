// lifegen's runtime (docs/lifegen_scope.md 4.2, docs/unreal_export.md "lifegen's runtime (LG0)"):
// copied into a project and built by `citygen unreal` beside CityGenPlay and CityGenAtmos.

using UnrealBuildTool;

public class CityGenLife : ModuleRules
{
	public CityGenLife(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		// Mass (the entities and processors, engine modules) and ZoneGraph (the lanes, a plugin)
		PrivateDependencyModuleNames.AddRange(new string[] { "MassCore", "MassEntity", "ZoneGraph" });
		// LG4: the place slots are Smart Objects of the world's subsystem (its definitions' types
		// are in the public header CityGenLifePlaces.h, hence public)
		PublicDependencyModuleNames.AddRange(new string[] { "SmartObjectsModule", "GameplayTags", "WorldConditions" });
	}
}
