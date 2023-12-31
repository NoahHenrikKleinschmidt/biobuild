"""
Auxiliary tools for PDB files.
"""

from tabulate import tabulate

__amino_acids = set(
    (
        "ALA",
        "ARG",
        "ASN",
        "ASP",
        "CYS",
        "GLN",
        "GLU",
        "GLY",
        "HIS",
        "ILE",
        "LEU",
        "LYS",
        "MET",
        "PHE",
        "PRO",
        "SER",
        "THR",
        "TRP",
        "TYR",
        "VAL",
        "CSE",  # selenocysteines
        "SEC",
    )
)


def write_pdb(mol, filename, symmetric: bool = True):
    """
    Write a molecule to a PDB file.

    Parameters
    ----------
    mol : Molecule
        The molecule to write.
    filename : str
        The filename to write to.
    symmetric : bool, optional
        Whether to write the molecule in a symmetric way, by default True.
    """
    with open(filename, "w") as f:
        f.write(make_atoms_table(mol))
        f.write("\n")
        f.write(make_connect_table(mol, symmetric))
        f.write("\nEND\n")


def write_connect_lines(mol, filename):
    """
    Write "CONECT" lines to a PDB file.
    This is necessary since Biopython by default does not do that...

    Parameters
    ----------
    mol : bb.Molecule
        The molecule to generate the connectivity for.
    filename : str
        The filename to write to.
    """
    with open(filename, "r") as f:
        c = f.read()
    with open(filename, "w") as f:
        f.write(c.replace("END", "").rstrip())
        f.write("\n")
        f.write(make_connect_table(mol))
        f.write("\nEND\n")


def parse_connect_lines(filename):
    """
    Parse "CONECT" lines from a PDB file.
    This is necessary since Biopython by default does not do that...

    Parameters
    ----------
    filename : str
        The filename to parse.

    Returns
    -------
    bonds: list
        A list of tuples of atom serial numbers that are bonded.
    """
    with open(filename, "r") as f:
        lines = f.readlines()
    bonds = {}
    known_bonds = set()
    for line in lines:
        if line.startswith("CONECT"):
            # split the line into tokens of length 5
            line = line[6:]
            tokens = [
                line[i : i + 5].strip()
                for i in range(0, len(line), 5)
                if len(line[i : i + 5].strip()) > 0
            ]

            atom_a = int(tokens[0])
            for token in tokens[1:]:
                b = (atom_a, int(token))
                # make sure we don't add the same bond twice
                if b[::-1] in known_bonds:
                    continue
                bonds.setdefault(b, 0)
                bonds[b] += 1
                known_bonds.add(b)
    return [(*k, v) for k, v in bonds.items()]


def make_connect_table(mol, symmetric=True):
    """
    Make a "CONECT" table for a PDB file.
    This is necessary since Biopython by default does not do that...

    Parameters
    ----------
    mol : Molecule
        The molecule to generate the connectivity for.
    symmetric : bool, optional
        Whether to generate symmetric bonds (i.e. if A is bonded to B, then
        B is bonded to A as well). Default is True. And both are written to the file.

    Returns
    -------
    connect_lines : str
        The lines to add to the PDB file.
    """
    connectivity = {}
    for bond in mol.get_bonds():
        a = bond.atom1.serial_number
        b = bond.atom2.serial_number
        if a not in connectivity:
            connectivity[a] = [b] * bond.order
        else:
            connectivity[a].extend([b] * bond.order)

        if symmetric:
            if b not in connectivity:
                connectivity[b] = [a] * bond.order
            else:
                connectivity[b].extend([a] * bond.order)

    lines = []
    for atom in connectivity:
        line = "CONECT" + left_adjust(str(atom), 5)
        for c in connectivity[atom]:
            line += left_adjust(str(c), 5)
            if len(line) > 70:
                lines.append(line)
                line = "CONECT" + left_adjust(str(atom), 5)
        lines.append(line)
    return "\n".join(lines)


# atom_line = "{prefix}{serial}{neg_adj}{element}{id}{altloc}{residue} {chain}{res_serial}{icode}    {x}{y}{z}{occ}{temp}       {seg}{element}{charge}"
atom_line = "{prefix}{serial}{neg_adj}{id}{altloc}{residue} {chain}{res_serial}{icode}    {x}{y}{z}{occ}{temp}       {seg}{element}{charge}"


def make_atoms_table(mol):
    """
    Make a PDB atom table

    Parameters
    ----------
    mol : bb.Molecule
        The molecule to generate the table for.

    Returns
    -------
    str
        The table
    """
    lines = []
    for atom in mol.get_atoms():
        neg_adj = " "
        # if len(atom.id) > 3:
        #     neg_adj = ""
        #     altloc_len = 2
        # else:
        #     neg_adj = " "
        # altloc_len = 1
        if atom.pqr_charge is None:
            charge = ""
        else:
            charge = str(int(atom.pqr_charge)) + ("-" if atom.pqr_charge < 0 else "+")

        if atom.get_parent().resname in __amino_acids:
            prefix = "ATOM  "
        else:
            prefix = "HETATM"

        lines.append(
            atom_line.format(
                prefix=prefix,
                serial=left_adjust(str(atom.serial_number), 5),
                neg_adj=neg_adj,
                id=right_adjust(atom.id.upper(), 4),
                # id=right_adjust(
                #     atom.id.replace(atom.element.upper(), "").replace(
                #         atom.element.title(), ""
                #     ),
                #     2,
                # ),
                altloc=right_adjust(atom.altloc, 1),
                residue=left_adjust(atom.get_parent().resname, 3),
                chain=atom.get_parent().get_parent().id,
                # resseq=left_adjust(" ", 3),
                res_serial=left_adjust(str(atom.get_parent().id[1]), 3),
                icode=" ",  # atom.get_parent().id[2],
                x=left_adjust(f"{atom.coord[0]:.3f}", 8),
                y=left_adjust(f"{atom.coord[1]:.3f}", 8),
                z=left_adjust(f"{atom.coord[2]:.3f}", 8),
                # occ=left_adjust("1.00", 6),
                occ=left_adjust(f"{atom.occupancy:.2f}", 6),
                # temp=left_adjust("0.00", 6),
                temp=left_adjust(f"{atom.bfactor:.2f}", 6),
                seg=right_adjust("", 3),
                element=left_adjust(atom.element.upper(), 2),
                charge=left_adjust(charge, 2),
            )
        )
    return "\n".join(lines)


def right_adjust(s, n):
    """
    Right adjust a string to a certain length.

    Parameters
    ----------
    s : str
        The string to adjust.
    n : int
        The length to adjust to.

    Returns
    -------
    str
        The adjusted string.
    """
    return s + " " * (n - len(s))


def left_adjust(s, n):
    """
    Left adjust a string to a certain length.

    Parameters
    ----------
    s : str
        The string to adjust.
    n : int
        The length to adjust to.

    Returns
    -------
    str
        The adjusted string.
    """
    return " " * (n - len(s)) + s
