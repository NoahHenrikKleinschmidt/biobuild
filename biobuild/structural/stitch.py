"""
Functions to stitch molecules together even in the absence of a patch
"""

from typing import Union

import networkx as nx
import numpy as np
from copy import deepcopy

import Bio.PDB as bio

import biobuild.core.Molecule as Molecule
import biobuild.core.Linkage as Linkage
import biobuild.structural.connector as base
import biobuild.optimizers as optimizers
import biobuild.utils.abstract as abstract


class Stitcher(base.Connector):
    """
    This class is responsible for stitching molecules together
    when there is not a patch available which specifies the immediate
    geometry of their connection. The only required input is a pair of atoms
    that should form a new bond, and two tuples of atoms (at least one from each molecule)
    that are being removed in the process.

    Parameters
    ----------
    copy_target : bool
        Whether to copy the target molecule before stitching
    copy_source : bool
        Whether to copy the source molecule before stitching
    """

    def __init__(self, copy_target: bool = False, copy_source: bool = False):
        super().__init__(copy_target, copy_source)
        self._removals = (None, None)
        self._policy = None, None

    def apply(
        self,
        target: "Molecule.Molecule",
        source: "Molecule.Molecule",
        target_removals: tuple,
        source_removals: tuple,
        target_atom: Union[int, bio.Atom.Atom] = None,
        source_atom: Union[int, bio.Atom.Atom] = None,
        target_residue: Union[int, bio.Residue.Residue] = None,
        source_residue: Union[int, bio.Residue.Residue] = None,
        optimization_steps: int = 1e4,
        **kwargs,
    ) -> "Molecule.Molecule":
        """
        Stitch the source and target molecules together

        Parameters
        ----------
        target : Molecule
            The target molecule
        source : Molecule
            The source molecule. This will be attached to the target molecule.
        target_removals : tuple
            A tuple of atoms to be removed from the target molecule. These must be the atom's ids within the attaching residue.
            All atoms must be part fo the same residue as the attaching `target_atom`.
        source_removals : tuple
            A tuple of atoms to be removed from the source molecule. These must be the atom's ids within the attaching residue.
            All atoms must be part fo the same residue as the attaching `source_atom`.
        target_atom : int or bio.Atom.Atom
            The atom on the target molecule to which the source molecule will be attached. This may either be the atom object directly or its serial number.
            If none is provided, the molecule's "root atom" is used (if defined).
        source_atom : int or bio.Atom.Atom
            The atom on the source molecule to which the target molecule will be attached. This may either be the atom object directly or its serial number.
            If none is provided, the molecule's "root atom" is used (if defined).
        target_residue : int or Residue
            The residue hosting the target atom. This is only required if the target atom is not given directly or specified by name.
        source_residue : int or Residue
            The residue hosting the source atom. This is only required if the source atom is not given directly or specified by name.
        optimization_steps : int, optional
            The number of steps to take in the optimization process, by default 1e4
        **kwargs
            Additional keyword arguments to pass to the optimizer. See the documentation for `biobuild.optimizers.agents.optimize` for more details.

        Returns
        -------
        tuple
            The target and source molecules after stitching. At this point, the source molecule is aligned
            to the target molecules but not yet integrated into it. Use the `merge` method to do this.
        """

        if self.copy_target:
            target = deepcopy(target)
            if target_atom in target.atoms:
                target_atom = target.get_atom(target_atom.serial_number)
        if self.copy_source:
            source = deepcopy(source)
            if source_atom in source.atoms:
                source_atom = source.get_atom(source_atom.serial_number)

        self.target = target
        self.source = source

        self._anchors = self.get_anchors(
            (target_atom, source_atom), target_residue, source_residue
        )
        self._removals = self._find_removals(target_removals, source_removals)

        self._align_anchors()

        self._remove_atoms()
        self._optimize(optimization_steps, **kwargs)

        return self.target, self.source

    def _align_anchors(self):
        """
        Align the anchor atoms such that they are in the right positions to form a bond
        This will move the source molecule such that its anchor atom is in the position
        of one of the target molecule's removed atoms
        """
        neighs = self.target.get_neighbors(self._anchors[0])
        ref_target_atom = next(i for i in neighs if i in self._removals[0])

        neighs = self.source.get_neighbors(self._anchors[1])
        ref_source_atom = next(i for i in neighs if i in self._removals[1])

        # self._v.draw_point("anchor target", self._anchors[0].coord, color="blue")
        # self._v.draw_point("anchor source", self._anchors[1].coord, color="blue")
        # self._v.draw_point("ref_target_atom", ref_target_atom.coord, color="red")
        # self._v.draw_point("ref_source_atom", ref_source_atom.coord, color="red")

        _old_coords = np.stack(
            [
                self._anchors[1].coord,
                ref_source_atom.coord,
            ]
        )
        _new_coords = np.array(
            [
                ref_target_atom.coord,
                self._anchors[0].coord,
            ]
        )

        # compute translation vector
        old_centroid = _old_coords.mean(axis=0)
        new_centroid = _new_coords.mean(axis=0)
        translation_vector = new_centroid - old_centroid

        _relative_old_coords = _old_coords - old_centroid
        _relative_new_coords = _new_coords - new_centroid

        H = (_relative_old_coords).T.dot(_relative_new_coords)
        U, S, VT = np.linalg.svd(H)
        R = VT.T @ U.T

        # self._v.draw_edges(self.source.bonds, color="black", opacity=0.5)
        atom_coords = np.array([atom.coord for atom in self.source.get_atoms()])
        atom_coords = (
            (R @ (atom_coords - old_centroid).T).T + old_centroid + translation_vector
        )
        for coord, atom in zip(atom_coords, self.source.get_atoms()):
            atom.set_coord(coord)

        # for atom in self.source.get_atoms():
        #     vec = atom.coord - old_centroid
        #     new_coord = (R @ vec) + old_centroid + translation_vector
        #     atom.set_coord(new_coord)

        # self._v.draw_edges(self.source.bonds, color="orange", opacity=0.5)
        # self._v.draw_point("anchor source (new)", self._anchors[1].coord, color="teal")

    def _find_removals(self, target_removals, source_removals):
        """
        Find the atoms to remove from the target and source molecules
        while stitching them together
        """
        _target_removals = [
            self._target_residue.child_dict[atom]
            for atom in target_removals
            if atom in self._target_residue.child_dict
        ]
        _source_removals = [
            self._source_residue.child_dict[atom]
            for atom in source_removals
            if atom in self._source_residue.child_dict
        ]
        return (set(_target_removals), set(_source_removals))

    def _remove_atoms(self):
        """
        Remove the atoms specified in the removals list
        """
        # self.target._remove_atoms(*self._removals[0])
        # self.source._remove_atoms(*self._removals[1])
        # return
        mapping = {
            0: self.target,
            1: self.source,
        }
        for i, removals in enumerate(self._removals):
            obj = mapping[i]

            for atom in removals:
                obj._AtomGraph.remove_node(atom)
                bonds = (
                    i
                    for i in obj._bonds
                    if atom.full_id == i[0].full_id or atom.full_id == i[1].full_id
                )
                for bond in bonds:
                    obj._bonds.remove(bond)
                p = atom.get_parent()
                p.detach_child(atom.id)
                atom.set_parent(p)

            adx = 1
            for atom in obj._model.get_atoms():
                atom.set_serial_number(adx)
                adx += 1

    def _optimize(self, steps: int = 1e4, **kwargs):
        """
        Optimize the geometry of the source molecule

        Parameters
        ----------
        steps : int
            The number of optimization steps to perform
        """

        tmp = Molecule.empty(self.target.id)
        self.target.adjust_indexing(self.source)

        tmp.add_residues(
            self._target_residue,
            self._source_residue,
            adjust_seqid=False,
            _copy=True,
        )

        bonds = self.target.get_bonds(self._target_residue)
        bonds.extend(self.source.get_bonds(self._source_residue))
        for b in bonds:
            b = (b[0].serial_number, b[1].serial_number)
            tmp.add_bond(*b)
        tmp.add_bond(self._anchors[0].serial_number, self._anchors[1].serial_number)

        graph = tmp.make_residue_graph()
        graph.make_detailed(include_outliers=True, include_heteroatoms=True, f=1.2)

        edges = sorted(tmp.get_residue_connections())
        env = optimizers.MultiBondRotatron(graph, edges)

        best, _ = optimizers.scipy_optimize(env, int(steps), **kwargs)
        self._policy = edges, best

        # self.best.append(best)
        # f, reward, *_ = env.step(best)
        # self.rewards.append(reward)

        # self.env = env

    def merge(self) -> "Molecule.Molecule":
        """
        Merge the source molecule into the target molecule
        """
        self.target.add_residues(*self.source.residues)
        self.target._bonds.extend(self.source.bonds)
        self.target._AtomGraph.migrate_bonds(self.source._AtomGraph)
        self.target.add_bond(self._anchors[0], self._anchors[1])
        # self.target.reindex()

        # v = bb.utils.visual.MoleculeViewer3D(self.target)

        if self._policy[0] is not None:
            edges, angles = self._policy

            for bond, angle in zip(edges, angles):
                bond = (bond[0].full_id, bond[1].full_id)
                if len(self.target.get_bonds(*bond, either_way=False)) == 0:
                    self.target.add_bond(*bond)

                bond = self.target.get_bonds(*bond, either_way=False)[0]

                # v.draw_vector(
                #     "rotation",
                #     bond[0].coord,
                #     1.1 * (bond[1].coord - bond[0].coord),
                #     color="orange",
                # )

                self.target.rotate_around_bond(
                    *bond, np.degrees(angle), descendants_only=True
                )

            self._policy = None, None

        # v.draw_edges(self.target.bonds, color="red")
        # v.show()
        return self.target


__default_keep_keep_stitcher__ = Stitcher(False, False)
"""
Default stitcher for the case that both molecules are kept
"""

__default_keep_copy_stitcher__ = Stitcher(False, True)
"""
Default stitcher for the case that the target molecule is kept and the source molecule is copied
"""

__default_copy_copy_stitcher__ = Stitcher(True, True)
"""
Default stitcher for the case that both molecules are copied
"""


def stitch(
    target: "Molecule.Molecule",
    source: "Molecule.Molecule",
    recipe: "Linkage" = None,
    target_removals: tuple = None,
    source_removals: tuple = None,
    target_atom: Union[int, bio.Atom.Atom] = None,
    source_atom: Union[int, bio.Atom.Atom] = None,
    target_residue: Union[int, bio.Residue.Residue] = None,
    source_residue: Union[int, bio.Residue.Residue] = None,
    optimization_steps: int = 1e4,
    copy_target: bool = False,
    copy_source: bool = False,
    **kwargs,
) -> "Molecule.Molecule":
    """
    Stitch two molecules together.
    Thereby the source molecule is integrated into the target molecule.

    Parameters
    ----------
    target : Molecule
        The target molecule
    source : Molecule
        The source molecule. This will be attached to the target molecule.
    recipe : AbstractRecipe
        The recipe to be used for stitching. If none is provided, the stitching instructions can be submitted manually via the other parameters.
    target_removals : tuple
        This parameter is only used if no recipe is provided.
        A tuple of atoms to be removed from the target molecule. These must be the atom's ids within the attaching residue.
        All atoms must be part fo the same residue as the attaching `target_atom`.
    source_removals : tuple
        This parameter is only used if no recipe is provided.
        A tuple of atoms to be removed from the source molecule. These must be the atom's ids within the attaching residue.
        All atoms must be part fo the same residue as the attaching `source_atom`.
    target_atom : int or bio.Atom.Atom
        This parameter is only used if no recipe is provided.
        The atom on the target molecule to which the source molecule will be attached. This may either be the atom object directly or its serial number.
        If none is provided, the molecule's "root atom" is used (if defined).
    source_atom : int or bio.Atom.Atom
        This parameter is only used if no recipe is provided.
        The atom on the source molecule to which the target molecule will be attached. This may either be the atom object directly or its serial number.
        If none is provided, the molecule's "root atom" is used (if defined).
    target_residue : int or Residue
        The residue hosting the target atom. This is only required if the target atom is not given directly or specified by name. If a recipe is provided, the "attach_residue" is used by default. A ValueError is raised if none is defined.
    source_residue : int or Residue
        The residue hosting the source atom. This is only required if the source atom is not given directly or specified by name. If a recipe is provided, the "attach_residue" is used by default. A ValueError is raised if none is defined.
    optimization_steps : int, optional
        The number of steps to take in the optimization process, by default 1e4
    copy_target : bool, optional
        Whether to copy the target molecule before stitching, by default False
    copy_source : bool, optional
        Whether to copy the source molecule before stitching, by default False
    **kwargs
        Additional keyword arguments to pass to the optimizer. See the documentation for `biobuild.optimizers.agents.optimize` for more details.

    Returns
    -------
    Molecule
        The stitched molecule
    """
    if recipe is not None:
        if target_residue is None:
            if target.attach_residue is None:
                target_residue = target.residues[-1]
                # raise ValueError(
                #     "A residue in the target molecule must be provided or the target molecule must define an attachment residue"
                # )
            else:
                target_residue = target.attach_residue
        if source_residue is None:
            if source.attach_residue is None:
                source_residue = source.residues[-1]
                # raise ValueError(
                #     "A residue in the source molecule must be provided or the source molecule must define an attachment residue"
                # )
            else:
                source_residue = source.attach_residue

        return stitch(
            target=target,
            source=source,
            target_removals=recipe.deletes[0],
            source_removals=recipe.deletes[1],
            target_atom=recipe.bonds[0][0],
            source_atom=recipe.bonds[0][1],
            target_residue=target_residue,
            source_residue=source_residue,
            optimization_steps=optimization_steps,
            **kwargs,
        )

    # =====================

    if copy_source:
        source = deepcopy(source)
    if copy_target:
        target = deepcopy(target)
    __default_keep_keep_stitcher__.apply(
        target=target,
        source=source,
        target_removals=target_removals,
        source_removals=source_removals,
        target_atom=target_atom,
        source_atom=source_atom,
        target_residue=target_residue,
        source_residue=source_residue,
        optimization_steps=optimization_steps,
        **kwargs,
    )
    return __default_keep_keep_stitcher__.merge()


if __name__ == "__main__":
    import biobuild as bb

    ser = bb.Molecule.from_pubchem("SER")
    ser.autolabel()

    mol3 = bb.Molecule.from_pubchem("tert-butyl acetate")
    # mol3.autolabel()

    # attach the red bit to the serine
    l1 = bb.linkage("C6", "O3", ["H12"], ["HO3"])

    out = stitch(mol3, ser, l1)
    out.show()
    # import biobuild as bb

    # glc = bb.Molecule.from_compound("GLC")
    # glc.repeat(4, "14bb")

    # glc2 = bb.Molecule.from_compound("GLC")

    # prot = bb.core.Scaffold.from_pdb(
    #     "/Users/noahhk/GIT/biobuild/support/examples/4tvp.prot.pdb"
    # )
    # prot.infer_bonds(restrict_residues=False)
    # s = Stitcher(True, True)

    # res = prot.find()[0]

    # s.apply(prot, glc, target_removals=(""))

    # # ---------------------------------------------
    # # This is a very nice code piece down here...
    # # ---------------------------------------------
    # # glc2.rotate_around_bond(6, 5, 68)
    # # glc2.rotate_around_bond(3, 4, 41)

    # # v = None
    # # n = 200
    # # with alive_progress.alive_bar(n) as bar:
    # #     for i in range(n):
    # #         s = Stitcher(True, True)
    # #         s.apply(glc, glc2, ("O1", "HO1"), ("HO4",), "C1", "O4", 1e4)
    # #         new_glc = s.merge()

    # #         if v is None:
    # #             v = bb.utils.visual.MoleculeViewer3D(new_glc)
    # #         else:
    # #             v.draw_edges(new_glc.bonds, color="red", opacity=0.02)
    # #         bar()
    # # if v: v.show()

    # # import pandas as pd
    # # import seaborn as sns
    # # import matplotlib.pyplot as plt

    # # df = pd.DataFrame(s.best, columns=["phi", "psi"])
    # # df["reward"] = s.rewards
    # # ax = sns.jointplot(data=df, x="phi", y="psi", kind="kde")
    # # sns.scatterplot(data=df, x="phi", y="psi", hue="reward", ax=ax.ax_joint)

    # # plt.show()
    # # pass
