# Linked-image fixtures

`objdump -d` of the three V14 variants, taken verbatim from a clean ARM build
whose declared artifacts compared byte-identical against a second clean build
at the same path.

They are here because the alternative is a hand-written stand-in, and this
contract already learned what that costs: the source gate was verified against
1027 synthetic fixtures and refused its own generator the first time it met a
real one. Nothing in this directory is edited. The negative tests derive their
inputs by mutating these files at run time, so an attack fixture is a stated
difference from a real image rather than a second opinion about what one looks
like.

Regenerate only from a build whose determinism was checked, and update the
digests the unit suite pins.
