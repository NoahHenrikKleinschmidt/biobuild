"""
NEEDS NEW DOCSTRING
"""

import biobuild.utils as utils

def patch(atom1, atom2, internal_coordinates:dict, delete_in_target:list=None, delete_in_source:list = None, id:str=None) -> "Linkage":
    """
    Make a new `Linkage` instance that describes a "patch" between two molecules.
    A patch is a linkage that can be applied purely geometrically and does not require numeric optimization.
    As such, it requires the internal coordinates of the atoms in the immediate vicinity of the newly formed bond.

    Parameters
    ----------
    atom1 : str or tuple of str
        The atom in the first molecule to connect.
    atom2 : str or tuple of str
        The atom in the second molecule to connect.
    internal_coordinates : dict
        The internal coordinates of the atoms in the immediate vicinity of the newly formed bond.
        This must be a dictionary where keys are tuples of four atoms ids and values tuples containing (in order):
            - the bond length between the first and second atom
            - the bond length between the third and fourth atom
            - the bond angle between the first, second and third atom
            - the bond angle between the second, third and fourth atom
            - the dihedral angle between the first, second, third and fourth atom
    delete_in_target : str or tuple of str, optional
        The atom(s) in the first molecule to delete.
    delete_in_source : str or tuple of str, optional
        The atom(s) in the second molecule to delete.
    id : str, optional
        The id of the linkage.
    
    Returns
    -------
    Linkage
        The new linkage.
    """
    return linkage(atom1, atom2, delete_in_target=delete_in_target, delete_in_source=delete_in_source, internal_coordinates=internal_coordinates, id=id)

def recipe(atom1, atom2, delete_in_target:list=None, delete_in_source:list=None, id:str=None) -> "Linkage":
    """
    Make a new `Linkage` instance that describes a "recipe" to connect two molecules.
    A recipe is a linkage that can be applied numerically and requires numeric optimization as it does not
    have the internal coordinates of the atoms in the immediate vicinity of the newly formed bond.
    
    Parameters
    ----------
    atom1 : str or tuple of str
        The atom in the first molecule to connect.
    atom2 : str or tuple of str
        The atom in the second molecule to connect.
    delete_in_target : str or tuple of str, optional
        The atom(s) in the first molecule to delete.
    delete_in_source : str or tuple of str, optional
        The atom(s) in the second molecule to delete.
    id : str, optional
        The id of the linkage.
    
    Returns
    -------
    Linkage
        The new linkage.
    """
    return linkage(atom1, atom2, delete_in_target=delete_in_target, delete_in_source=delete_in_source, id=id)


def linkage(atom1, atom2, delete_in_target:list=None, delete_in_source:list=None, internal_coordinates:dict=None, id:str=None) -> "Linkage":
    """
    Make a new `Linkage` instance to connect two molecules together.

    Parameters
    ----------
    atom1 : str or tuple of str
        The atom in the first molecule to connect.
    atom2 : str or tuple of str
        The atom in the second molecule to connect.
    delete_in_target : str or tuple of str, optional
        The atom(s) in the first molecule to delete.
    delete_in_source : str or tuple of str, optional
        The atom(s) in the second molecule to delete.
    internal_coordinates : dict, optional
        The internal coordinates of the atoms in the immediate vicinity of the newly formed bond.
        If provided, the link can be applied purely geometrically and will not require numeric optimization.
        If provided, this must be a dictionary where keys are tuples of four atoms ids and values tuples containing (in order):
            - the bond length between the first and second atom
            - the bond length between the third and fourth atom
            - the bond angle between the first, second and third atom
            - the bond angle between the second, third and fourth atom
            - the dihedral angle between the first, second, third and fourth atom
    id : str, optional
        The ID of the linkage.

    Returns
    -------
    Linkage
        The new linkage instance.
    """
    # make a new linkage
    new_linkage = Linkage(id=id)

    # add the bond
    new_linkage.add_bond((atom1, atom2))

    # add the atoms to delete
    if delete_in_target is not None:
        new_linkage.add_delete(delete_in_target, "target")
    if delete_in_source is not None:
        new_linkage.add_delete(delete_in_source, "source")

    # add the internal coordinates
    if internal_coordinates is not None:
        if not isinstance(internal_coordinates, dict):
            raise TypeError("The internal coordinates must be provided as a dictionary.")
        for ic in _dict_to_ics(internal_coordinates):
            new_linkage.add_internal_coordinates(ic)

    # return the linkage
    return new_linkage

class Linkage(utils.abstract.AbstractEntity_with_IC):
    """
    Using the `Linkage` class, a template reaction instruction is stored for attaching molecules to one another.
    """

    def __init__(self, id=None) -> None:
        super().__init__(id)
        self._delete_ids = []

    @property
    def deletes(self):
        """
        Returns the atom IDs to delete
        in a tuple of lists where the first list
        contains the atom IDs to delete from the
        first structure (target) and the second one from the second structure (source)
        """
        deletes = (
            [i[1:] for i in self._delete_ids if i[0] == "1"],
            [i[1:] for i in self._delete_ids if i[0] == "2"],
        )
        return deletes

    def add_delete(self, id, _from:str=None):
        """
        Add an atom ID to delete

        Parameters
        ----------
        id : str
            The atom ID to delete.
        _from : str, optional
            The structure from which to delete the atom.
            Can be either "source" or "target". If not provided,
            the structure is inferred from the atom ID, in which case either `1` (target) or `2` (source) must be the first character of the ID.
        """
        if _from is None:
            if not id[0] in ["1", "2"]:
                raise ValueError("The atom ID must start with either 1 or 2 to indicate from which structure it is to be deleted.")
        else:
            if _from == "source":
                id = "2" + id
            elif _from == "target":
                id = "1" + id
            else:
                raise ValueError("The _from argument must be either 'source' or 'target'.")
        self._delete_ids.append(id)

    add_id_to_delete = add_delete


def _dict_to_ics(_dict):
    """
    Convert a dictionary of internal coordinates to a list of `InternalCoordinate` instances.
    """
    ics = []
    for key, value in _dict.items():    
        if len(key) == 4 and len(value) == 5:
            ic = utils.ic.InternalCoordinates(*key, *value)
        elif len(key) != 4:
                raise ValueError("The internal coordinate must be provided as a tuple of four atom IDs.")
        elif len(value) != 5:
            raise ValueError("The internal coordinate must be provided as a tuple of five values.")
        ics.append(ic)