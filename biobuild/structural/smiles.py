"""
Functions for handling SMILES strings
"""

try:
    from openbabel import pybel

    use_openbabel = True
except ImportError:
    use_openbabel = False

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    use_rdkit = True
except ImportError:
    use_rdkit = False

import biobuild.utils.convert as convert

if not use_openbabel and not use_rdkit:

    def read_smiles(smiles: str, add_hydrogens: bool = True):
        raise ImportError("Could not import either OpenBabel or RDKit")

    def make_smiles(structure):
        raise ImportError("Could not import either OpenBabel or RDKit")

elif use_rdkit:

    def read_smiles(smiles: str, add_hydrogens: bool = True):
        """
        Read a SMILES string using RDKit

        Parameters
        ----------
        smiles : str
            The SMILES string to read
        add_hydrogens : bool
            Whether to add hydrogens to the structure

        Returns
        -------
        Chem.Mol
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Could not parse SMILES string {smiles}")

        if add_hydrogens:
            mol = Chem.AddHs(mol)

        AllChem.EmbedMolecule(mol)
        AllChem.UFFOptimizeMolecule(mol)

        return mol

    def make_smiles(
        molecule: "Molecule", isomeric: bool = True, add_hydrogens: bool = False
    ) -> str:
        """
        Generate a SMILES string from a molecule

        Parameters
        ----------
        molecule : Molecule
            The molecule to convert
        isomeric : bool
            Whether to include isomeric information
        add_hydrogens : bool
            Whether to add hydrogens to the SMILES string
        Returns
        -------
        smiles : str
            The SMILES string
        """
        rdmol = molecule.to_rdkit()
        if not add_hydrogens:
            rdmol = Chem.RemoveHs(rdmol)
        return Chem.MolToSmiles(rdmol, isomericSmiles=isomeric)

elif use_openbabel:

    def read_smiles(smiles: str, add_hydrogens: bool = True):
        """
        Read a SMILES string using OpenBabel

        Parameters
        ----------
        smiles : str
            The SMILES string to read
        add_hydrogens : bool
            Whether to add hydrogens to the structure

        Returns
        -------
        pybel.Molecule
        """
        mol = pybel.readstring("smi", smiles)
        if mol is None:
            raise ValueError(f"Could not parse SMILES string {smiles}")
        mol.make3D()

        if not add_hydrogens:
            mol.removeh()
        return mol

    def make_smiles(
        molecule: "Molecule", isomeric: bool = True, add_hydrogens: bool = False
    ) -> str:
        """
        Generate a SMILES string from a molecule

        Parameters
        ----------
        molecule : Molecule
            The molecule to convert
        isomeric : bool
            Whether to include isomeric information
        add_hydrogens : bool
            Whether to add hydrogens to the SMILES string

        Returns
        -------
        smiles : str
            The SMILES string
        """
        obmol = molecule.to_pybel()
        if not add_hydrogens:
            obmol.removeh()
        return obmol.write("smi", isomeric=isomeric)


__all__ = [
    "read_smiles",
    "make_smiles",
    "use_openbabel",
    "use_rdkit",
]
