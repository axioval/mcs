# IFC geometry clearance example

This example demonstrates the authoring boundary:

- `openbim.ifc` owns exact IFC4X3 entity names and release identity;
- the Axioval engine owns `axioval:capability.component-clearance`, whose
  whole parameter signature the rule definition declares;
- MCS owns the rule definition, applicability, parameters, and normalized output.

The rule asks for a volume 200 mm deep, as wide and as high as each pipe
segment, on its left and right, free of walls. The package does **not** claim
that this defines a particular geometric algorithm. Implementations must
satisfy the capability contract and report their own scoped conformance.

`schema/adapters/Geometry.pkl` still lowers `openbim.geometry` capability IDs
such as `openbim.geometry:clearance.directional`, but no engine executes those
IDs today. A definition meant for the Axioval engine names the engine's
capability, here `axioval:capability.component-clearance`.
