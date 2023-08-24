"""
Test the behaviour of CHARMM force fields and the abstract classes that store their behaviour
"""

import biobuild as bb
import tests.base as base


def test_default_settings():
    top = bb.resources.get_default_topology()
    assert top is not None, "No topology is made"


def test_make_charmm_topology():
    top = bb.resources.charmm.CHARMMTopology()
    assert top is not None, "No topology is made"

    top = bb.resources.charmm.CHARMMTopology.from_file(base.CHARMM_TOPOLOGY_FILE)
    assert top is not None, "No topology is made"

    assert len(top.patches) == 12


# def test_residue():
#     top = bb.resources.get_default_topology()

#     assert top.has_residue("MAN"), "No mannose found!"
#     man = top.get_residue("MAN")

#     assert len(man.atoms) == 24
#     assert len(man.bonds) == 24

#     assert len(man.get_internal_coordinates()) == 22
#     assert len(man.get_internal_coordinates("C1", "C2", "C3", "O3")) == 1
#     assert len(man.get_internal_coordinates("C1", "C2", "C3", None)) == 0
#     assert (
#         len(man.get_internal_coordinates("C1", "C2", None, "O3", mode="partial")) == 1
#     )
#     assert (
#         len(man.get_internal_coordinates("C1", None, None, "O3", mode="partial")) == 1
#     )
#     assert len(man.get_internal_coordinates("C1", "O3", mode="anywhere_partial")) == 13
#     assert len(man.get_internal_coordinates("C1", "O3", mode="anywhere")) == 1

#     assert man.get_bond("C1", "C2") is not None
