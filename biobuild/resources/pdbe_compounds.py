"""
This module defines a Parser to extract information from the PDBE compound library.

Reading the PDBE Compound Library
=================================

The PDBE Compound Library is a database of small molecules that are found in PDB structures. It can be downloaded as an mmCIF file. 
`biobuild` provides a parser to extract information from the mmCIF file.

To parse a PDBE Compound Library file, we can use the toplevel function `read_compounds` or use the `PDBECompounds` class directly

.. code-block:: python

    import biobuild
    from biobuild.resources import PDBECompounds

    compounds = bb.read_compounds("path/to/pdbe-compounds.cif")
    # or 
    compounds = PDBECompounds.from_file("path/to/pdbe-compounds.cif")

Saving and loading PDBECompounds
================================

Because parsing may be an intensive operation, the `PDBECompounds` class implements a `save` method to save the parsed data to a pickle file.
For future sessions the pre-parsed object can be directly loaded using the `load` method. Naturally, both operations also have a functional equivalent.

.. code-block:: python

    # save an existing PDBECompounds object
    compounds.save("path/to/pdbe-compounds.pkl")
    # or 
    bb.save_compounds("path/to/pdbe-compounds.pkl", compounds)
    
    # load a pre-parsed PDBECompounds object
    compounds = PDBECompounds.load("path/to/pdbe-compounds.pkl")
    # or (read_compounds also supports loading)
    compounds = bb.read_compounds("path/to/pdbe-compounds.pkl")

In order to export data from the PDBE compounds library, the `PDBECompounds` class also implements a `to_json` method to export the data as a JSON file.
The JSON file can be loaded again using the `from_json` class method (or using `read_compounds` function). This is useful for sharing compound data with others
who may use different versions of `biobuild` and thus may have issues with pickeled objects, or for sharing data with other programs.

.. code-block:: python

    # save an existing PDBECompounds object
    compounds.to_json("path/to/pdbe-compounds.json")
    # or
    bb.export_compounds("path/to/pdbe-compounds.json", compounds)

    
Working with PDBECompounds
==========================

The `PDBECompounds` class provides a dictionary-like interface to the compounds in the library. It supports a number of query methods unified within the `get`. 
Compounds can be obtained from the library from their 3-letter _PDB ID_, their _name_, _chemical formula_, or _SMILES_ or _InChI_ string.


.. code-block:: python

    # get a compound by its PDB ID
    glc = compounds.get("GLC")

    # get a compound by its name
    glc = compounds.get("alpha d-glucose", by="name")

    # get a compound by its chemical formula
    glc = compounds.get("C6 H12 O6", by="formula")

    # get a compound by its SMILES string
    glc = compounds.get("C([C@@H]1[C@H]([C@@H]([C@H](O[C@@H]1O)O)O)O)O", by="smiles")

    # get a compound by its InChI string (note the "InChI=" prefix)
    # THIS ALSO USES `by="smiles"`!
    glc = compounds.get("InChI=1S/C6H12O6/c7-1-2-3(8)4(9)5(10)6(11)12-2/h2-11H,1H2/t2-,3-,4+,5-,6-/m1/s1", by="smiles")

    
By default the `get` method will create a `Molecule` object from the compound. Other output formats such as `biopython.Structure` or simple `dict` are also supported and can be specified using the `return_type` argument.
If multiple compounds match a query, they are returned as a list (unless `return_type` is a dictionary, in which they are kept as a dictionary).    


.. code-block:: python

    # get a compound as a `biobuild.Structure` object
    glc = compounds.get("GLC", return_type="structure")

    # get a compound as a `dict`
    glc = compounds.get("GLC", return_type="dict")

    

Setting default PDBECompounds
=============================

_biobuild_ loads a default PDBECompounds object for convenience. The default instance can be accessed using the `get_default_compounds` function. A custom instance can be set as the default using the `set_default_compounds` function.

.. code-block:: python

    import biobuild as bb

    # get the default PDBECompounds instance
    compounds = bb.get_default_compounds()

    # ... do something with the compounds

    # set a custom PDBECompounds instance as the default
    bb.set_default_compounds(compounds)

.. warning::

    The `set_default_compounds` has an additional keyword argument `overwrite` which is set to `False` by default. If set to `True` the default instance
    is permanently overwritten by the new one and will be used automatically by all future sessions. This is not recommended as it may lead to unexpected behaviour.
    

If the user is only interested in working with the default instance rather than a specific `PDBECompounds` instance, there are a number of toplevel functions available to short-cut the process.

For instance, in order to get the compound glucose from the default instance, we can do

.. code-block:: python

    # instead of doing
    compounds = bb.get_default_compounds()
    glc = compounds.get("GLC", return_type="dict")

    # we can do
    glc = bb.get_compound("GLC", return_type="dict")

Other toplevel functions indlude `has_compound` and `add_compound`.

"""

import os
import warnings
import numpy as np
import pdbecif.mmcif_tools as mmcif_tools
import pickle

import Bio.PDB as bio
from Bio import SVDSuperimposer

import biobuild.utils.json as json
import biobuild.utils.defaults as defaults
import biobuild.utils.auxiliary as aux
import biobuild.core.base_classes as base_classes
import biobuild.core.Molecule as Molecule

__loaded_compounds__ = {
    "sugars": False,
    "lipids": False,
    "small_molecules": False,
    "amino_acids": False,
    "nucleotides": False,
}

__to_float__ = {
    "_chem_comp": set(
        (
            "formula_weight",
            "pdbx_formal_charge",
        )
    ),
}

__to_delete__ = {
    "_chem_comp": set(
        (
            "pdbx_type",
            "mon_nstd_parent_comp_id",
            "pdbx_synonyms",
            "pdbx_initial_date",
            "pdbx_modified_date",
            "pdbx_release_status",
            "pdbx_ambiguous_flag",
            "pdbx_replaced_by",
            "pdbx_replaces",
            "pdbx_processing_site",
            "pdbx_model_coordinates_details",
            "pdbx_model_coordinates_db_code",
            "pdbx_ideal_coordinates_details",
            "pdbx_subcomponent_list",
            "pdbx_model_coordinates_missing_flag",
            "pdbx_ideal_coordinates_missing_flag",
        )
    ),
}

# a list of categories to ignore while parsing
__to_ignore__ = [
    "_pdbx_chem_comp_audit",
    "_pdbx_chem_comp_feature",
]

__needs_to_have__ = set(
    (
        "_chem_comp",
        "_pdbx_chem_comp_descriptor",
        "_pdbx_chem_comp_identifier",
        "_chem_comp_atom",
        "_chem_comp_bond",
    )
)

__search_by__ = ("id", "name", "formula", "smiles")


_bond_order_rev_map = {
    "SING": 1,
    "DOUB": 2,
    "TRIP": 3,
}
"""
Reverse map of bond order names to numbers.
"""

_bond_order_map = {
    1: "SING",
    2: "DOUB",
    3: "TRIP",
}
"""
Map of bond order numbers to names.
"""


def read_compounds(filename: str, set_default: bool = True) -> "PDBECompounds":
    """
    Reads a PDBECompounds object from a CIF, JSON, or pickle file.

    Parameters
    ----------
    filename : str
        The path to the file to read.
    set_default : bool, optional
        Whether to set the read PDBECompounds object as the default.
        Defaults to True.

    Returns
    -------
    PDBECompounds
        The PDBECompounds object parsed from the file.
    """
    if filename.endswith(".cif"):
        compounds = PDBECompounds.from_file(filename)
    elif filename.endswith(".json"):
        compounds = PDBECompounds.from_json(filename)
    elif filename.endswith(".pkl") or filename.endswith(".pickle"):
        compounds = PDBECompounds.load(filename)
    else:
        raise ValueError(
            "Unsupported file format. Only CIF, JSON and pickle (.pkl or .pickle) files are supported."
        )
    if set_default:
        set_default_compounds(compounds)
    return compounds


def save_compounds(filename: str, compounds: "PDBECompounds" = None):
    """
    Saves a PDBECompounds object to a file.

    Parameters
    ----------
    filename : str
        The path to the pickle file to save to.

    compounds : PDBECompounds, optional
        The PDBECompounds object to save. If not provided, the default
        PDBECompounds object is used.
    """
    if compounds is None:
        compounds = get_default_compounds()
    compounds.save(filename)


def export_compounds(filename: str, compounds: "PDBECompounds" = None):
    """
    Export the PDBECompounds object to a JSON file.

    Parameters
    ----------
    filename : str
        The path to the JSON file to save to.

    compounds : PDBECompounds, optional
        The PDBECompounds object to save. If not provided, the default
        PDBECompounds object is used.
    """
    if compounds is None:
        compounds = get_default_compounds()
    compounds.to_json(filename)


def has_compound(compound: str, search_by: str = None) -> bool:
    """
    Checks if a given compound is available in the currently loaded default
    PDBECompounds instance.

    Parameters
    ----------
    compound : str
        The compound to check.

    search_by : str, optional
        The type of search to perform. One of `id`, `name`, `formula`, `smiles` (includes `inchi`).
        By default, all search types are used.
    """
    if search_by is not None:
        return get_default_compounds().has_residue(compound, by=search_by)

    for by in __search_by__:
        if get_default_compounds().has_residue(compound, by=by):
            return True
    return False


def get_compound(compound: str, search_by: str = None, return_type: str = "molecule"):
    """
    Get a compound from the currently loaded default PDBECompounds instance.

    Parameters
    ----------
    compound : str
        The compound to get.

    search_by : str, optional
        The type of search to perform. One of `id`, `name`, `formula`, `smiles` (includes `inchi`).
        By default, all search types are used.

    return_type : str, optional
        The type of object to return. One of `molecule` (a biobuild Molecule), `structure` (a biobuild structure only, does not include connectivity), `dict` (the compound data and coordinate dictionaries).
        Defaults to `molecule`.

    Returns
    -------
    object or list
        The molecule object, structure, or tuple of dictionaries.
        If multiple compounds are found matching, they are returned as a list.
    """
    if not has_compound(compound, search_by=search_by):
        raise ValueError(
            f"Compound {compound} not found in the default PDBECompounds instance."
        )
    comps = get_default_compounds()
    for by in __search_by__:
        if comps.has_residue(compound, by=by):
            comp = comps.get(compound, by=by, return_type=return_type)
            if return_type == "dict":
                if isinstance(comp, list):
                    comp = [(c, comps._pdb[c["id"]]) for c in comp]
                else:
                    comp = comp, comps._pdb[comp["id"]]
            return comp


def add_compound(
    mol: "Molecule",
    type: str = None,
    names: list = None,
    identifiers: list = None,
    formula: str = None,
    overwrite: bool = False,
):
    """
    Add a compound to the currently loaded default PDBECompounds instance.

    Parameters
    ----------
    mol : Molecule
        The molecule to add.
    type : str, optional
        The type of compound. For instance `protein`, `dna`, `rna`, `ligand`, `water`, `ion`, `other`.
    names : list, optional
        A list of names for the compound.
    identifiers : list, optional
        A list of identifiers for the compound.
    formula : str, optional
        The chemical formula of the compound.
    overwrite : bool, optional
        Whether to hardcode overwrite the current default PDBECompounds instance.
        This will make the compound available for all future sessions.
    """
    get_default_compounds().add(
        mol, type=type, names=names, identifiers=identifiers, formula=formula
    )
    if overwrite:
        set_default_compounds(get_default_compounds(), overwrite=True)


def get_default_compounds() -> "PDBECompounds":
    """
    Get the currently loaded default PDBECompounds instance.

    Returns
    -------
    PDBECompounds
        The currently loaded default PDBECompounds instance.
    """
    return defaults.__default_instances__["PDBECompounds"]


def set_default_compounds(obj, overwrite: bool = False):
    """
    Set a PDBECompounds object as the new default.

    Parameters
    ----------
    obj : PDBECompounds
        The PDBECompounds object to set as the new default
    overwrite : bool
        If set to `True`, the new object will be permanently saved as
        the default. Otherwise, the new object will only be used for
        the current session.
    """
    if not obj.__class__.__name__ == "PDBECompounds":
        raise TypeError("The object must be a PDBECompounds instance.")
    if overwrite:
        current = defaults.get_default_instance("PDBECompounds")
        if current:
            current.to_json(defaults.DEFAULT_PDBE_COMPONENT_FILES["base"] + ".bak")
    defaults.__default_instances__["PDBECompounds"] = obj
    if overwrite:
        obj.to_json(defaults.DEFAULT_PDBE_COMPONENT_FILES["base"])


def restore_default_compounds(overwrite: bool = True):
    """
    Restore the default PDBECompounds object from the backup file

    Parameters
    ----------
    overwrite : bool
        If set to `True`, the backup file will be permanently saved as the default again.
    """
    if not os.path.isfile(defaults.DEFAULT_PDBE_COMPONENT_FILES["base"] + ".bak"):
        raise FileNotFoundError(
            "No backup file found. The default PDBECompounds object has not been modified."
        )
    defaults.__default_instances__["PDBECompounds"] = PDBECompounds.from_json(
        defaults.DEFAULT_PDBE_COMPONENT_FILES["base"] + ".bak"
    )
    if overwrite:
        os.rename(
            defaults.DEFAULT_PDBE_COMPONENT_FILES["base"] + ".bak",
            defaults.DEFAULT_PDBE_COMPONENT_FILES["base"],
        )


def load_amino_acids():
    """
    Load amino acid components into the default PDBECompounds instance.
    """
    if __loaded_compounds__["amino_acids"]:
        return
    comps = get_default_compounds()
    amino_acids = PDBECompounds.from_json(
        defaults.DEFAULT_PDBE_COMPONENT_FILES["amino_acids"]
    )
    comps.merge(amino_acids)
    __loaded_compounds__["amino_acids"] = True


def load_lipids():
    """
    Load lipid components into the default PDBECompounds instance.
    """
    if __loaded_compounds__["lipids"]:
        return
    comps = get_default_compounds()
    lipids = PDBECompounds.from_json(defaults.DEFAULT_PDBE_COMPONENT_FILES["lipids"])
    comps.merge(lipids)
    __loaded_compounds__["lipids"] = True


def load_sugars():
    """
    Load sugar components into the default PDBECompounds instance.
    """
    if __loaded_compounds__["sugars"]:
        return
    comps = get_default_compounds()
    sugars = PDBECompounds.from_json(defaults.DEFAULT_PDBE_COMPONENT_FILES["sugars"])
    comps.merge(sugars)
    __loaded_compounds__["sugars"] = True


def load_nucleotides():
    """
    Load nucleotide components into the default PDBECompounds instance.
    """
    if __loaded_compounds__["nucleotides"]:
        return

    comps = get_default_compounds()
    nucleotides = PDBECompounds.from_json(
        defaults.DEFAULT_PDBE_COMPONENT_FILES["nucleotides"]
    )
    comps.merge(nucleotides)
    __loaded_compounds__["nucleotides"] = True


def load_small_molecules():
    """
    Load small molecule components into the default PDBECompounds instance.
    """
    if __loaded_compounds__["small_molecules"]:
        return
    comps = get_default_compounds()
    small_molecules = PDBECompounds.from_json(
        defaults.DEFAULT_PDBE_COMPONENT_FILES["small_molecules"]
    )
    comps.merge(small_molecules)
    __loaded_compounds__["small_molecules"] = True


def load_all_compounds():
    """
    Load all available components into the default PDBECompounds instance.
    """
    load_amino_acids()
    load_lipids()
    load_sugars()
    load_nucleotides()
    load_small_molecules()


class PDBECompounds:
    """
    This class wraps a dictionary of PDBE compounds.
    It facilitates easy data access and searchability for compounds.

    Parameters
    ----------
    compounds : dict
        A dictionary of PDBE compounds.
    id : str, optional
        The ID of the PDBECompounds object. Defaults to None.
    """

    def __init__(self, compounds: dict, id=None) -> None:
        self.id = id
        self._compounds = {k: None for k in compounds.keys()}
        self._pdb = dict(self._compounds)
        self._setup_dictionaries(compounds)

        self._filename = None
        self._orig = compounds

    @classmethod
    def from_file(cls, filename: str) -> "PDBECompounds":
        """
        Create a PDBECompounds object from a `cif` file.

        Parameters
        ----------
        filename : str
            The path to the file.

        Returns
        -------
        PDBECompounds
            The PDBECompounds object.
        """
        _dict = mmcif_tools.MMCIF2Dict()
        _dict = _dict.parse(filename, ignoreCategories=__to_ignore__)

        # Make sure all required fields are present
        _keys = set(_dict.keys())
        for key in _keys:
            v = _dict[key]
            if not all(i in v.keys() for i in __needs_to_have__):
                del _dict[key]
                warnings.warn(
                    f"Compound '{key}' does not have all required fields. It will be ignored."
                )

        new = cls(_dict)
        new._filename = filename
        return new

    @classmethod
    def load(self, filename: str) -> "PDBECompounds":
        """
        Load a PDBECompounds object from a `pickle` file.

        Parameters
        ----------
        filename : str
            The path to the file.

        Returns
        -------
        PDBECompounds
            The PDBECompounds object.
        """
        with open(filename, "rb") as f:
            return pickle.load(f)

    @classmethod
    def from_json(cls, filename: str) -> "PDBeCompounds":
        """
        Make a PDBECompounds object from a previously exported `json` file.

        Parameters
        ----------
        filename : str
            The path to the file.

        Returns
        -------
        PDBECompounds
            The PDBECompounds object.
        """
        _dict = json.read(filename)
        new = cls._from_dict(_dict)
        new._filename = filename
        return new

    @classmethod
    def _from_dict(cls, _dict: dict) -> "PDBECompounds":
        """
        Make a PDBECompounds object from a dictionary.

        Parameters
        ----------
        _dict : dict
            The dictionary to use.

        Returns
        -------
        PDBECompounds
            The PDBECompounds object.
        """
        new = cls({}, id=_dict["id"])
        for compound in _dict["compounds"]:
            comp_dict = {
                "id": compound["id"],
                "name": compound["names"][0],
                "type": compound["type"],
                "formula": compound["formula"],
                "one_letter_code": compound["one_letter_code"],
                "three_letter_code": compound["three_letter_code"],
                "names": compound["names"],
                "descriptors": compound["identifiers"],
            }
            mol = Molecule._from_dict(compound)
            pdb_dict = _molecule_to_pdbx_dict(mol)

            new._compounds[compound["id"]] = comp_dict
            new._pdb[compound["id"]] = pdb_dict

        return new

    @property
    def ids(self) -> list:
        """
        Get a list of all compound ids.

        Returns
        -------
        list
            A list of all compound ids.
        """
        return list(self._compounds.keys())

    @property
    def formulas(self) -> list:
        """
        Get a list of all compound formulas.

        Returns
        -------
        list
            A list of all compound formulas.
        """
        return [i["formula"] for i in self._compounds.values()]

    def save(self, filename: str = None) -> None:
        """
        Save the PDBECompounds object to a `pickle` file.

        Parameters
        ----------
        filename : str
            The path to the file. By default the same file used to load the object is used.
            If no file is available, a `ValueError` is raised.
        """
        if filename is None:
            if self._filename is None:
                raise ValueError("No filename specified.")
            filename = self._filename

        if not filename.endswith(".pkl"):
            filename = aux.change_suffix(filename, ".pkl")

        self._filename = filename

        with open(filename, "wb") as f:
            pickle.dump(self, f)

    def to_json(self, filename: str = None) -> None:
        """
        Export the PDBECompounds object to a `json` file.

        Parameters
        ----------
        filename : str
            The path to the file. By default the same file used to load the object is used.
            If no file is available, a `ValueError` is raised.
        """
        if filename is None:
            if self._filename is None:
                raise ValueError("No filename specified.")
            filename = self._filename

        if not filename.endswith(".json"):
            filename = aux.change_suffix(filename, ".json")

        json.write_pdbe_compounds(self, filename)

    def merge(self, other: "PDBECompounds") -> None:
        """
        Merge another compounds dictionary into this one.

        Parameters
        ----------
        other : PDBECompounds
            The other object.
        """
        for key in other._compounds.keys():
            if key in self._compounds:
                warnings.warn(
                    f"Compound '{key}' already present. It will be overwritten."
                )
            self._compounds[key] = other._compounds[key]
            self._pdb[key] = other._pdb[key]

    def get(
        self,
        query: str,
        by: str = "id",
        return_type: str = "molecule",
    ):
        """
        Get a compound that matches the given criteria.

        Parameters
        ----------
        query : str
            The query to search for.

        by : str, optional
            The type of query, by default "id". Possible values are:
            - "id": search by compound id
            - "name": search by compound name (must match any available synonym exactly)
            - "formula": search by compound formula
            - "smiles": search by compound smiles (this also works for inchi)

        return_type : str, optional
            The type of object to return, by default "molecule". Possible values are:
            - "molecule": return a biobuild `Molecule` object
            - "dict": return a dictionary of the compound data
            - "structure": return a biopython `Structure` object
            - "residue": return a biopython `Residue` object

        Returns
        -------
        object
            The object that matches the given criteria, or None if no match was found.
            If multiple matches are found, a list of objects is returned.
        """
        _dict = self._get(query, by)
        if len(_dict.keys()) == 0:
            return None
        elif len(_dict.keys()) > 1:
            return [self.get(i, "id", return_type) for i in _dict.keys()]

        _dict = list(_dict.values())[0]
        if return_type == "molecule":
            return self._molecule(_dict)
        elif return_type == "dict":
            return _dict
        elif return_type == "structure":
            return self._make_structure(_dict)
        elif return_type == "residue":
            res = self._make_residue(_dict)
            self._fill_residue(res, _dict)
            return res
        else:
            raise ValueError(f"Invalid return_type '{return_type}'.")

    def add(
        self,
        mol: Molecule,
        type: str = None,
        names: list = None,
        identifiers: list = None,
        formula: str = None,
        one_letter_code: str = None,
        three_letter_code: str = None,
    ):
        """
        Add a compound to the dictionary.

        Parameters
        ----------
        mol : Molecule
            The compound to add.
        type : str, optional
            The type of compound, e.g. "ligand", "cofactor", etc.
        names : list, optional
            A list of names for the compound.
        identifiers : list, optional
            A list of identifiers such as SMILES or InChI for the compound.
        formula : str, optional
            The formula of the compound. If not given, it will be calculated from the molecule.
        """
        if names is None:
            names = []
        if identifiers is None:
            identifiers = []
        if formula is None:
            formula = aux.make_formula(mol.get_atoms())

        # get the residue
        comp = {
            "id": mol.id,
            "names": set(i.lower() for i in names),
            "formula": formula,
            "descriptors": identifiers,
            "type": type,
            "one_letter_code": one_letter_code,
            "three_letter_code": three_letter_code,
        }
        comp["names"].add(mol.id.lower())
        self._compounds[mol.id] = comp

        pdb = _molecule_to_pdbx_dict(mol)
        self._pdb[mol.id] = pdb

    def remove(self, id: str) -> None:
        """
        Remove a compound from the dictionary.

        Parameters
        ----------
        id : str
            The id of the compound to remove.
        """
        self._compounds.pop(id, None)
        self._pdb.pop(id, None)

    def has_residue(self, query: str, by: str = "id") -> bool:
        """
        Check if a compound has a residue definition.

        Parameters
        ----------
        query : str
            The query to search for.

        by : str, optional
            The type of query, by default "id". Possible values are:
            - "id": search by compound id
            - "name": search by compound name (must match any available synonym exactly)
            - "formula": search by compound formula
            - "smiles": search by compound smiles (this also works for inchi)

        Returns
        -------
        bool
            True if the compound has a residue definition, False otherwise.
        """
        _dict = self._get(query, by)
        return len(_dict.keys()) > 0

    def translate_ids_3_to_1(self, ids: list) -> list:
        """
        Translate a list of 3-letter compound ids to 1-letter ids.
        Any ids that cannot be translated are returned as "X".

        Parameters
        ----------
        ids : list
            A list of 3-letter compound ids.

        Returns
        -------
        list
            A list of 1-letter compound ids.
        """
        new = []
        for i in ids:
            i = self.get(i, "id", "dict")
            i = i.get("one_letter_code", None)
            if i is None:
                i = "X"
            new.append(i)
        return new

    def translate_ids_1_to_3(self, ids: list) -> list:
        """
        Translate a list of 1-letter compound ids to 3-letter ids.
        Any unknown ids are replaced with "XXX".

        Parameters
        ----------
        ids : list
            A list of 1-letter compound ids.

        Returns
        -------
        list
            A list of 3-letter compound ids.
        """
        new = []
        for i in ids:
            i = self.get(i, "id", "dict")
            i = i.get("three_letter_code", None)
            if i is None:
                i = "XXX"
            new.append(i)
            return new

    def relabel_atoms(self, structure):
        """
        Relabel the atoms of a `Molecule` object to match the atom names of the given compound.

        Parameters
        ----------
        structure
            A `Molecule` object or biopython object holding at least one residue.

        Returns
        -------
        object
            The object with relabeled atoms.
        """
        imposer = SVDSuperimposer.SVDSuperimposer()
        for residue in structure.get_residues():
            # get a reference
            name = residue.resname
            ref = self.get(name, "id", "residue")
            if ref is None:
                warnings.warn(f"Could not find residue '{name}' in PDBECompounds.")
                continue

            residue_coords = np.asarray([atom.coord for atom in residue.get_atoms()])
            ref_coords = np.asarray([atom.coord for atom in ref.get_atoms()])
            imposer.set(ref_coords, residue_coords)
            imposer.run()

            # get the residue coordinates
            new_coords = imposer.get_transformed()

            ref_atom_ids = [atom.id for atom in ref.get_atoms()]
            for idx, atom in enumerate(list(residue.get_atoms())):
                _new = new_coords[idx]
                min_idx = np.argmin(np.linalg.norm(ref_coords - _new, axis=1))
                atom.id = ref_atom_ids[min_idx]

        return structure

    def _get(self, q: str, by: str = "id"):
        """
        Get a dictionary of compounds that match the given criteria.

        Parameters
        ----------
        q : str
            The query to search for.
        by : str, optional
            The type of query, by default "id". Possible values are:
            - "id": search by compound id
            - "name": search by compound name (must match any available synonym exactly)
            - "formula": search by compound formula
            - "smiles": search by compound smiles (this also works for inchi)

        Returns
        -------
        dict
            A dictionary of compounds that match the given criteria.
        """
        if by == "id":
            _q = self._compounds.get(q)
            if _q is None:
                return {}
            return {q: _q}
        elif by == "name":
            return {k: v for k, v in self._compounds.items() if q.lower() in v["names"]}
        elif by == "formula":
            return {
                k: v
                for k, v in self._compounds.items()
                if q.upper().replace(" ", "") == v["formula"]
            }
        elif by == "smiles":
            return {k: v for k, v in self._compounds.items() if q in v["descriptors"]}
        else:
            raise ValueError(f"Invalid search type: {by}")

    def _setup_dictionaries(self, data_dict):
        """
        Fill in the dictionaries with the appropriate data

        Parameters
        ----------
        data_dict : dict
            A dictionary of data from the cif file.
        """
        for key, value in data_dict.items():
            comp = value["_chem_comp"]

            for k in __to_delete__["_chem_comp"]:
                if k in comp:
                    comp.pop(k)
            for k in __to_float__["_chem_comp"]:
                if k in comp:
                    comp[k] = float(comp[k])
            for k in comp:
                if comp[k] == "?":
                    comp[k] = None

            comp["descriptors"] = value["_pdbx_chem_comp_descriptor"]["descriptor"]

            comp["names"] = [comp["name"]]

            synonyms = value.get("_pdbx_chem_comp_synonyms", None)
            if synonyms:
                if not isinstance(synonyms["name"], list):
                    synonyms["name"] = [synonyms["name"]]
                comp["names"].extend(synonyms["name"])

            identifiers = value.get("_pdbx_chem_comp_identifier", None)
            if identifiers:
                if not isinstance(identifiers["identifier"], list):
                    identifiers["identifier"] = [identifiers["identifier"]]
                comp["names"].extend(identifiers["identifier"])

            comp["names"] = set(i.lower() for i in comp["names"])

            if comp["formula"] is not None:
                comp["formula"] = comp["formula"].replace(" ", "")

            self._compounds[key] = comp

            atoms = value["_chem_comp_atom"]
            bonds = value["_chem_comp_bond"]

            atoms["pdbx_model_Cartn_x_ideal"] = [
                i.replace("?", "NaN") for i in atoms["pdbx_model_Cartn_x_ideal"]
            ]
            atoms["pdbx_model_Cartn_y_ideal"] = [
                i.replace("?", "NaN") for i in atoms["pdbx_model_Cartn_y_ideal"]
            ]
            atoms["pdbx_model_Cartn_z_ideal"] = [
                i.replace("?", "NaN") for i in atoms["pdbx_model_Cartn_z_ideal"]
            ]
            atoms["charge"] = [i.replace("?", "NaN") for i in atoms["charge"]]

            pdb = {
                "atoms": {
                    "full_ids": [i.replace(",", "'") for i in atoms["atom_id"]],
                    "ids": [
                        i.replace(",", "'") for i in atoms["pdbx_component_atom_id"]
                    ],
                    "serials": np.array(atoms["pdbx_ordinal"], dtype=int),
                    "coords": np.array(
                        [
                            (float(i), float(j), float(k))
                            for i, j, k in zip(
                                atoms["pdbx_model_Cartn_x_ideal"],
                                atoms["pdbx_model_Cartn_y_ideal"],
                                atoms["pdbx_model_Cartn_z_ideal"],
                            )
                        ]
                    ),
                    "elements": atoms["type_symbol"],
                    "charges": np.array(atoms["charge"], dtype=float),
                    # ---------------------- FUTURE UPDATE ----------------------
                    # support multi-residue molecules
                    # we need a proper parsing way to extract the residue information
                    # from the pdbx mmcif files...
                    # ---------------------- FUTURE UPDATE ----------------------
                    "residue": [
                        1 for i in atoms["type_symbol"]
                    ],  # atoms["pdbx_component_comp_id"],
                },
                "bonds": {
                    "bonds": [
                        (a.replace(",", "'"), b.replace(",", "'"))
                        for a, b in zip(bonds["atom_id_1"], bonds["atom_id_2"])
                    ],
                    "parents": [(1, 1) for i in bonds["atom_id_1"]],
                    "orders": np.array(bonds["value_order"]),
                },
                "residues": {
                    "serials": [1],
                    "names": [atoms["pdbx_component_comp_id"][0]],
                },
            }
            self._pdb[key] = pdb

    def _molecule(self, compound: dict) -> Molecule:
        """
        Make a biobuild Molecule from a compound.

        Parameters
        ----------
        compound : dict
            A dictionary of a compound.

        Returns
        -------
        Molecule
            A biobuild Molecule.
        """
        pdb = self._pdb[compound["id"]]

        struct = self._make_structure(compound)
        mol = Molecule(struct)
        for bdx in range(len(pdb["bonds"]["bonds"])):
            a, b = pdb["bonds"]["bonds"][bdx]
            res_a, res_b = pdb["bonds"]["parents"][bdx]
            a = mol.get_atom(a, residue=res_a)
            b = mol.get_atom(b, residue=res_b)
            for _ in range(_bond_order_rev_map.get(pdb["bonds"]["orders"][bdx])):
                mol.add_bond(a, b)

        return mol

    def _make_structure(self, compound: dict) -> "bio.PDB.Structure":
        """
        Make a structure from a compound.

        Parameters
        ----------
        compound : dict
            A dictionary of a compound.

        Returns
        -------
        biobuild.Structure
            A structure.
        """
        if len(compound) == 0:
            return None

        struct = base_classes.Structure(compound["id"])
        model = base_classes.Model(0)
        struct.add(model)
        chain = base_classes.Chain("A")
        model.add(chain)
        for res in self._make_residues(compound):
            chain.add(res)
        # add atoms to residue (at the end to ensure that the residue's full id is propagated)
        self._fill_residues(chain, compound)
        return struct

    def _fill_residues(self, chain, compound: dict):
        """
        Fill a residue with atoms from a compound.

        Parameters
        ----------
        chain : biobuild.Chain
            A biobuild Chain with the residues to fill.
        compound : dict
            A dictionary of a compound.
        """
        pdb = self._pdb.get(compound["id"], None)
        if pdb is None:
            raise ValueError("No pdb data for compound.")

        atoms = pdb["atoms"]
        for i in range(len(atoms["ids"])):
            res = atoms["residue"][i]
            res = _residue_from_chain(res, chain)
            if res is None:
                res = chain.child_list[0]
            atom = base_classes.Atom(
                atoms["full_ids"][i],
                atoms["coords"][i],
                atoms["serials"][i],
                fullname=atoms["ids"][i],
                element=atoms["elements"][i],
                pqr_charge=atoms["charges"][i],
            )
            res.add(atom)

    def _make_residues(self, compound: dict) -> "Residue":
        """
        Make a residue from a compound.

        Parameters
        ----------
        compound : dict
            A dictionary of a compound.

        Yields
        -------
        Residue
            A residue.
        """
        if len(compound) == 0:
            return None
        pdb = self._pdb[compound["id"]]
        residues = pdb["residues"]
        for serial, name in zip(residues["serials"], residues["names"]):
            res = base_classes.Residue(name, " ", serial)
            yield res

    def __getitem__(self, key):
        return self._compounds[key], self._pdb[key]

    def __len__(self):
        return len(self._compounds)

    def __iter__(self):
        for key in self._compounds:
            yield key, self._compounds[key], self._pdb[key]


defaults.set_default_instance(
    "PDBECompounds",
    PDBECompounds.from_json(defaults.DEFAULT_PDBE_COMPONENT_FILES["base"]),
)


def _residue_from_chain(idx, chain):
    """
    Get a residue from a chain
    """
    return next((i for i in chain.child_list if i.id[1] == idx), None)


def _molecule_to_pdbx_dict(mol):
    """
    Make a pdbx dictionary from a molecule.
    """
    _bond_dict = {}
    for bond in mol.get_bonds():
        _bond_dict[bond] = _bond_dict.get(bond, 0) + 1

    pdb = {
        "atoms": {
            "full_ids": [i.id.replace(",", "'") for i in mol.get_atoms()],
            "ids": [i.id.replace(",", "'") for i in mol.get_atoms()],
            "serials": [i.serial_number for i in mol.get_atoms()],
            "coords": np.array(
                [
                    (float(i), float(j), float(k))
                    for i, j, k in zip(
                        (i.coord[0] for i in mol.get_atoms()),
                        (i.coord[1] for i in mol.get_atoms()),
                        (i.coord[2] for i in mol.get_atoms()),
                    )
                ]
            ),
            "elements": [i.element.title() for i in mol.get_atoms()],
            "charges": [i.pqr_charge for i in mol.get_atoms()],
            "residue": [i.parent.id[1] for i in mol.get_atoms()],
        },
        "bonds": {
            "bonds": [
                (a.id.replace(",", "'"), b.id.replace(",", "'"))
                for a, b in _bond_dict.keys()
            ],
            "parents": [
                (a.get_parent().id[1], b.get_parent().id[1])
                for a, b in _bond_dict.keys()
            ],
            "orders": [_bond_order_map.get(i) for i in _bond_dict.values()],
        },
        "residues": {
            "serials": [i.id[1] for i in mol.get_residues()],
            "names": [i.resname for i in mol.get_residues()],
        },
    }
    return pdb


__all__ = [
    "PDBECompounds",
    "set_default_compounds",
    "get_default_compounds",
    "restore_default_compounds",
    "get_compound",
    "has_compound",
    "add_compound",
    "read_compounds",
    "export_compounds",
    "save_compounds",
    "load_amino_acids",
    "load_nucleotides",
    "load_sugars",
    "load_lipids",
    "load_small_molecules",
    "load_all_compounds",
]


if __name__ == "__main__":
    f = "support/pdbe_compounds/test.cif"
    compounds = PDBECompounds.from_file(f)
    compounds.to_json("comps.json")
    c2 = PDBECompounds.from_json("comps.json")
    pass
    # from biobuild.core import Molecule

    # real = Molecule.from_compound("GLC")

    # scrambled = Molecule.from_compound("GLC")

    # counts = {"C": 0, "H": 0, "O": 0, "N": 0, "S": 0, "P": 0}
    # for atom in scrambled.atoms:
    #     counts[atom.element] += 1
    #     atom.id = atom.element + str(counts[atom.element])

    # print(scrambled.atoms)
    # compounds.relabel_atoms(scrambled)
    # print(scrambled.atoms)

    # from biobuild.utils.visual import MoleculeViewer3D

    # v = MoleculeViewer3D(scrambled)
    # v.show()
