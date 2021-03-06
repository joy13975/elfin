#!/usr/bin/env python3
import glob
import numpy as np
import codecs
import json
import argparse
import shutil
from collections import defaultdict
from collections import OrderedDict

import Bio.PDB

from utilities import *
from pdb_utilities import *

nested_dict = lambda: defaultdict(nested_dict)

def parse_args(args):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Generates the xdb database from preprocessed single and double modules.')
    parser.add_argument('--relaxed_pdbs_dir', default='./resources/pdb_prepped/')
    parser.add_argument('--metadata_dir', default='./resources/metadata/')
    parser.add_argument('--output', default='./resources/xdb.json')
    parser.add_argument('--aligned_pdb_dir', default='./resources/pdb_aligned/')
    return parser.parse_args(args)

def main(test_args=None):
    """main"""
    args = parse_args(sys.argv[1:] if test_args is None else test_args)

    XDBGenerator(
        args.relaxed_pdbs_dir,
        args.metadata_dir,
        args.aligned_pdb_dir,
        args.output
    ).run()

class XDBGenerator:
    def __init__(
        self,
        relaxed_pdbs_dir,
        metadata_dir,
        aligned_pdb_dir,
        out_file
    ):
        self.relaxed_pdbs_dir = relaxed_pdbs_dir
        module_types = ['doubles', 'singles', 'hubs']
        shutil.move('metadata','resources/metadata' )
        make_dir(aligned_pdb_dir)
        for mt in module_types:
            make_dir(aligned_pdb_dir + '/{}/'.format(mt))

        self.hub_info         = read_json(metadata_dir + '/hub_info.json')
        self.aligned_pdb_dir  = aligned_pdb_dir
        self.out_file         = out_file
        self.si               = Bio.PDB.Superimposer()
        self.modules          = nested_dict()
        self.n_to_c_tx        = []
        self.hub_tx           = []

        # Cache in memory because disk I/O is really heavy here
        self.single_pdbs      = defaultdict(dict)
        self.double_pdbs      = defaultdict(dict)

    def find_tip(self, term, struct, chain_id):
        term = term.lower()
        assert(term in {'c', 'n'})
        chain = get_chain(struct, chain_id=chain_id)
        residues = chain.child_list
        n = len(residues)
        divider = 6  # The smaller the divider, the closer to terminus.

        assert(n > 0)
        if term == 'n':
            start_idx, end_idx = 0, n//divider
        else:
            start_idx, end_idx = (divider-1)*n//divider, n

        sum_coord = np.asarray([0., 0., 0.])
        for r in residues[start_idx:end_idx]:
            sum_coord += r['CA'].get_coord().astype('float64')

        tip_vector = sum_coord/(end_idx - start_idx - 1)

        return tip_vector.tolist()


    def create_tx(self, mod_a, a_chain, mod_b, b_chain, rot, tran):
        tx_entry = \
            OrderedDict([
                ('mod_a', mod_a),
                ('mod_a_chain', a_chain),
                ('mod_b', mod_b),
                ('mod_b_chain', b_chain),
                ('rot', rot.tolist()),
                ('tran', np.asarray(tran).tolist())
            ])
        return tx_entry

    def process_hub(self, file_name):
        """Aligns a hub module to its A component (chain A), then computes the
        transform for aligning itself to its other components.
        """

        # Load structures
        hub = read_pdb(file_name)

        # Centre the hub
        self.move_to_origin(hub)

        hub_fusion_factor = 4

        hub_name = os.path.basename(file_name).replace('.pdb', '')
        hub_meta = self.hub_info.get(hub_name, None)
        assert(hub_meta != None)
        if hub_meta is None:
            raise ValueError('Could not get hub metadata for hub {}\n'.format(hub_name))

        # Create module entry first
        comp_data = hub_meta['component_data']
        del hub_meta['component_data']
        hub_meta['chains'] = {
                c.id: {
                        'single_name': comp_data[c.id]['single_name'],
                        'n': nested_dict(),
                        'n_tip': nested_dict(),
                        'c': nested_dict(),
                        'c_tip': nested_dict(),
                        'n_residues': len(c.child_list)
                    }  for c in hub.get_chains()
            }
        hub_meta['radii'] = self.get_radii(hub)
        self.modules['hubs'][hub_name] = hub_meta

        # The current process does not allow hub to hub connections. Maybe this
        # need to be changed?
        for hub_chain_id in comp_data:
            chain_data = comp_data[hub_chain_id]
            comp_name = chain_data['single_name']

            if chain_data['c_free']:
                b_name_gen = (tx['mod_b'] for tx in self.n_to_c_tx if tx['mod_a'] == comp_name)
                for single_b_name in b_name_gen:
                    # Compute the transformation required to move a single
                    # module B from its aligned position to the current hub's
                    # "finger tip".
                    #
                    # Here we do not use the second quadrant method, because during
                    # stitching none of the hubs' residues get changed. The stitching
                    # will take place at the end of the hub's component's terminal.
                    rc_hub_a = get_chain_residue_count(hub, hub_chain_id)
                    rc_dbl_a = get_pdb_residue_count(self.single_pdbs[comp_name])
                    fusion_count = int_ceil(float(rc_dbl_a) / hub_fusion_factor)
                    double = self.double_pdbs[comp_name][single_b_name]


                    # Compute transformation matrix.

                    # Find transform between component single and single b.
                    hub_single_chain_id = \
                        list(self.single_pdbs[comp_name].get_chains())[0].id
                    single_b_chain_id = \
                        list(self.single_pdbs[single_b_name].get_chains())[0].id

                    dbl_tx_id = self.modules['singles'][comp_name]['chains'] \
                        [hub_single_chain_id]['c'] \
                        [single_b_name][single_b_chain_id]

                    assert(dbl_tx_id is not None)
                    dbl_n_to_c = self.n_to_c_tx[dbl_tx_id]

                    dbl_tx = np.vstack(
                        (np.hstack((dbl_n_to_c['rot'], np.transpose([dbl_n_to_c['tran']]))),
                         [0,0,0,1])
                    )

                    # Find transform from hub to single A.
                    rot, tran = self.get_rot_trans(
                        fixed=hub,
                        fixed_chain_id=hub_chain_id,
                        moving=double,
                        fixed_resi_offset=rc_hub_a - fusion_count,
                        moving_resi_offset=rc_dbl_a - fusion_count,
                        match_count=fusion_count
                    )

                    # Rotation in BioPython is inversed.
                    rot = np.transpose(rot)

                    comp_to_single_tx = np.vstack(
                        (np.hstack((rot, np.transpose([tran]))),
                        [0,0,0,1])
                    )

                    # 1. Shift to hub's component frame.
                    # 2. Shift to double B frame.
                    dbl_raised_tx = np.matmul(comp_to_single_tx, dbl_tx);

                    # Decompose transform.
                    rot = dbl_raised_tx[:3, :3]
                    tran = dbl_raised_tx[:3, 3]

                    tx = self.create_tx(
                        hub_name,
                        hub_chain_id,
                        single_b_name,
                        single_b_chain_id,
                        rot,
                        tran)
                    tx_id = len(self.n_to_c_tx) + len(self.hub_tx)

                    self.modules['hubs'][hub_name]['chains'] \
                        [hub_chain_id]['c'] \
                        [single_b_name][single_b_chain_id] = tx_id

                    self.modules['hubs'][hub_name]['chains'] \
                        [hub_chain_id]['c_tip'] = \
                        self.find_tip('c', hub, hub_chain_id)

                    self.modules['singles'][single_b_name]['chains'] \
                        [single_b_chain_id]['n'] \
                        [hub_name][hub_chain_id] = tx_id

                    self.hub_tx.append(tx)

            if chain_data['n_free']:
                a_name_gen = (tx['mod_a'] for tx in self.n_to_c_tx if tx['mod_b'] == comp_name)
                for single_a_name in a_name_gen:
                    # Same as c_free except comp acts as single b
                    rc_a = get_pdb_residue_count(self.single_pdbs[single_a_name])
                    rc_b = get_pdb_residue_count(self.single_pdbs[comp_name])
                    fusion_count = int_ceil(float(rc_b) / hub_fusion_factor)
                    double = self.double_pdbs[single_a_name][comp_name]


                    # Compute transformation matrix.

                    # Find transform from double component B to hub component.
                    rot, tran = self.get_rot_trans(
                        fixed=hub,
                        fixed_chain_id=hub_chain_id,
                        moving=double,
                        fixed_resi_offset=0,      # start matching from the n-term of hub component, which is index 0
                        moving_resi_offset=rc_a,  # start matching at the beginning of single b in the double
                        match_count=fusion_count
                    )

                    # Rotation in BioPython is inversed.
                    rot = np.transpose(rot)

                    dbl_to_hub_tx = np.vstack(
                        (np.hstack((rot, np.transpose([tran]))),
                        [0,0,0,1])
                    )

                    # 1. Shift to hub frame - do nothing; just dbl_to_hub_tx.

                    # Decompose transform.
                    rot = dbl_to_hub_tx[:3, :3]
                    tran = dbl_to_hub_tx[:3, 3]

                    single_a_chain_id = \
                        list(self.single_pdbs[single_a_name].get_chains())[0].id

                    tx = self.create_tx(
                        single_a_name,
                        single_a_chain_id,
                        hub_name,
                        hub_chain_id,
                        rot,
                        tran)
                    tx_id = len(self.n_to_c_tx) + len(self.hub_tx)

                    self.modules['singles'][single_a_name]['chains'] \
                        [single_a_chain_id]['c'] \
                        [hub_name][hub_chain_id] = tx_id

                    self.modules['hubs'][hub_name]['chains'] \
                        [hub_chain_id]['n'] \
                        [single_a_name][single_a_chain_id] = tx_id

                    self.modules['hubs'][hub_name]['chains'] \
                        [hub_chain_id]['n_tip'] = \
                        self.find_tip('n', hub, hub_chain_id)

                    self.hub_tx.append(tx)

        save_pdb(
            struct=hub,
            path=self.aligned_pdb_dir + '/hubs/' + hub_name + '.pdb'
        )

    def process_double(self, file_name):
        """Aligns a double module to its A component and then computes the transform
        for aligning to its B component. Saves aligned structure to output folder.
        """
        # Step 1: Load structures
        double = read_pdb(file_name)

        # Preprocessed pdbs have only 1 chain
        assert(len(list(double.get_chains())) == 1)

        double_name = file_name.split('/')[-1].replace('.pdb', '')
        single_a_name, single_b_name = double_name.split('-')

        single_a = self.single_pdbs[single_a_name]
        single_b = self.single_pdbs[single_b_name]

        rc_a = get_pdb_residue_count(single_a)
        rc_b = get_pdb_residue_count(single_b)
        rc_double = get_pdb_residue_count(double)

        rc_a_half = int_floor(float(rc_a)/2)
        rc_b_half = int_ceil(float(rc_b)/2)

        # fusion_factor should be deprecated in favour of "core range".
        dbl_fusion_factor = 8
        fusion_count_a = int_ceil(float(rc_a) / dbl_fusion_factor)
        fusion_count_b = int_ceil(float(rc_b) / dbl_fusion_factor)

        # Step 2: Move double to align with the first single.
        self.align(
            moving=double,
            fixed=single_a,
            moving_resi_offset=rc_a_half - fusion_count_a,
            fixed_resi_offset=rc_a_half - fusion_count_a,
            match_count=fusion_count_a
        )

        # Step 3: Get COM of the single_b as seen in the double.
        com_b = self.get_centre_of_mass(
            single_b,
            mother=double,
            child_resi_offset=rc_b_half - fusion_count_b,
            mother_resi_offset=rc_a + rc_b_half - fusion_count_b,
            match_count=fusion_count_b
        )

        # Step 4: Get transformation of single B to part B inside double.
        #
        #   Double is already aligned to first single so there is no need for
        # the first transformation.
        #
        #   Only align residues starting from the middle of single B because
        #   the middle suffers the least from interfacing displacements.
        rot, tran = self.get_rot_trans(
            moving=double,
            fixed=single_b,
            moving_resi_offset=rc_a + rc_b_half - fusion_count_b,
            fixed_resi_offset=rc_b_half - fusion_count_b,
            match_count=fusion_count_b
        )

        # Rotation in BioPython is inversed.
        rot = np.transpose(rot)

        # Inverse result transform because we want the tx that takes the
        # single B module to part B inside double.
        tmp_tx = np.vstack(
            (np.hstack((rot, np.transpose([tran]))),
            [0,0,0,1])
        )

        inv_tx = np.linalg.inv(tmp_tx);

        # Decompose transform.
        rot = inv_tx[:3, :3]
        tran = inv_tx[:3, 3]

        # Step 5: Save the aligned molecules.
        #
        # Here the PDB format adds some slight floating point error. PDB is
        # already phased out so and we should really consider using mmCIF for
        # all modules.
        save_pdb(
            struct=double,
            path=self.aligned_pdb_dir + '/doubles/' + double_name + '.pdb'
        )

        single_a_chain_id = list(single_a.get_chains())[0].id
        single_b_chain_id = list(single_b.get_chains())[0].id
        tx = self.create_tx(
            single_a_name,
            single_a_chain_id,
            single_b_name,
            single_b_chain_id,
            rot,
            tran)
        tx_id = len(self.n_to_c_tx)

        self.modules['singles'][single_a_name]['chains'] \
            [single_a_chain_id]['c'][single_b_name][single_b_chain_id] = tx_id
        self.modules['singles'][single_b_name]['chains'] \
            [single_b_chain_id]['n'][single_a_name][single_a_chain_id] = tx_id
        self.n_to_c_tx.append(tx)

        # Cache structure in memory
        self.double_pdbs[single_a_name][single_b_name] = double

    def process_single(self, file_name):
        """Centres a single module and saves to output folder."""
        single_name = file_name.split('/')[-1].replace('.pdb', '')
        single = read_pdb(file_name)

        # Preprocessed pdbs have only 1 chain
        assert(len(list(single.get_chains())) == 1)

        # Check that there is only one chain
        chain_list = list(single.get_chains())
        if len(chain_list) != 1:
            raise ValueError('Single PDB contains {} chains!\n'.format(len(chain_list)))

        self.move_to_origin(single)
        save_pdb(
            struct=single,
            path=self.aligned_pdb_dir + '/singles/' + single_name + '.pdb'
        )

        self.modules['singles'][single_name] = {
                'chains': {
                    chain_list[0].id: {
                        'n': nested_dict(),
                        'c': nested_dict(),
                        'n_residues': len(chain_list[0].child_list)
                    }
                },
                'radii': self.get_radii(single)
            }

        # Cache structure in memory
        self.single_pdbs[single_name] = single

    def dump_xdb(self):
        """Writes alignment data to a json file."""
        to_dump = \
            OrderedDict([
                ('modules', self.modules),
                ('n_to_c_tx', self.n_to_c_tx)
            ])

        json.dump(to_dump,
            open(self.out_file, 'w'),
            separators=(',', ':'),
            ensure_ascii=False,
            indent=4)

    def get_centre_of_mass(
        self,
        child,
        mother=None,
        child_resi_offset=0,
        mother_resi_offset=0,
        match_count=-1
    ):
        """Computes centre-of-mass coordinate of a Bio.PDB.Structure.Structure.

        Args:
        - child - Bio.PDB.Structure.Structure for which the centre-of-mass should
            be calculated.
        - mother - Bio.PDB.Structure.Structure onto which child is to be first
            aligned.
        - moving_resi_offset - the residue offset of the moving
            Bio.PDB.Structure.Structure when extracting carbon alpha coordinates.
        - fixed_resi_offset - the residue offset of the fixed
            Bio.PDB.Structure.Structure when extracting carbon alpha coordinates.
        - match_count - number of residues from which carbon alpha coordinates are
            extracted.

        Returns:
        - com - 3x1 numpy array of the centre-of-mass.
        """
        CAs = [r['CA'].get_coord().astype('float64') for r in child.get_residues()]
        com = np.mean(CAs, axis=0)

        if mother is not None:
            # This is for finding COM of a single inside a double
            _, tran = self.get_rot_trans(
                moving=child,
                fixed=mother,
                moving_resi_offset=child_resi_offset,
                fixed_resi_offset=mother_resi_offset,
                match_count=match_count
            )

            com += tran
        return com

    def get_radii(self, pose):
        """Computes three different measures of the radius.

        Args:
        - pose - Bio.PDB.Structure.Structure

        Returns:
        - _ - an dict containing: average of all atoms distances, max
            carbon alpha distance, and max heavy atom distance, each calculated
            against the centre-of-mass.
        """
        if not pose.at_origin:
            raise ValueError('get_radii() must be called with centered modules.')

        natoms = 0;
        rg_sum = 0;
        max_ca_dist = 0;

        nHeavy = 0;
        max_heavy_dist = 0;
        for a in pose.get_atoms():
            dist = np.linalg.norm(
                a.get_coord().astype('float64'));

            rg_sum += dist;

            if(a.name =='CA'):
                max_ca_dist = max(max_ca_dist, dist);

            if(a.element != 'H'):
                max_heavy_dist = max(max_heavy_dist, dist);
                nHeavy = nHeavy + 1;

            natoms = natoms + 1;

        average_all = rg_sum / natoms;
        return {
                'average_all': average_all,
                'max_ca_dist': max_ca_dist,
                'max_heavy_dist': max_heavy_dist
            }

    def move_to_origin(self, pdb):
        """Centres a Bio.PDB.Structure.Structure to the global origin."""
        com = self.get_centre_of_mass(pdb)

        # No rotation - just move to centre
        pdb.transform([[1,0,0],[0,1,0],[0,0,1]], -com)

        # Tag the pdb
        pdb.at_origin = True

    def align(
        self,
        **kwargs
    ):
        """Moves the moving Bio.PDB.Structure.Structure to the fixed
        Bio.PDB.Structure.Structure.
        """
        moving = kwargs.pop('moving')
        fixed = kwargs.pop('fixed')
        moving_resi_offset = kwargs.pop('moving_resi_offset', 0)
        fixed_resi_offset = kwargs.pop('fixed_resi_offset', 0)
        match_count = kwargs.pop('match_count', -1)

        rot, tran = self.get_rot_trans(
            moving=moving,
            fixed=fixed,
            moving_resi_offset=moving_resi_offset,
            fixed_resi_offset=fixed_resi_offset,
            match_count=match_count
        )

        # BioPython's own transform() deals with the inversed rotation
        # correctly.
        moving.transform(rot, tran)

    def get_rot_trans(
        self,
        **kwargs
    ):
        """Computes the rotation and transformation matrices using BioPython's
        superimposer.

        Args:
        - moving - the Bio.PDB.Structure.Structure that is to move towards the
            other (fixed).
        - fixed - the Bio.PDB.Structure.Structure that the other (moving) is to
            align to.
        - moving_resi_offset - the residue offset of the moving
            Bio.PDB.Structure.Structure when extracting carbon alpha coordinates.
        - fixed_resi_offset - the residue offset of the fixed
            Bio.PDB.Structure.Structure when extracting carbon alpha coordinates.
        - match_count - number of residues from which carbon alpha coordinates are
            extracted.

        ----IMPORT NOTE----
        The rotation from BioPython is the second dot operand instead of the
        conventional first dot operand.

        This means instead of the standard R*v + T, the actual transform is done
        with v'*R + T.

        Hence, the resultant rotation matrix might need transposing if not
        passed back into BioPython.
        ----IMPORT NOTE----

        Returns:
        - (rot, tran) - a tuple containing the rotation and transformation
            matrices.
        """

        moving = kwargs.pop('moving')
        moving_chain_id = kwargs.pop('moving_chain_id', 'A')
        fixed = kwargs.pop('fixed')
        fixed_chain_id = kwargs.pop('fixed_chain_id', 'A')
        moving_resi_offset = kwargs.pop('moving_resi_offset', 0)
        fixed_resi_offset = kwargs.pop('fixed_resi_offset', 0)
        match_count = kwargs.pop('match_count', -1)


        moving_chain = get_chain(moving, chain_id=moving_chain_id)
        moving_residues = moving_chain.child_list \
            [moving_resi_offset:(moving_resi_offset+match_count)]
        ma = [r['CA'] for r in moving_residues]

        fixed_chain = get_chain(fixed, chain_id=fixed_chain_id)
        fixed_residues = fixed_chain.child_list \
            [fixed_resi_offset:(fixed_resi_offset+match_count)]
        fa = [r['CA'] for r in fixed_residues]

        self.si.set_atoms(fa, ma)
        return self.si.rotran

    def run(self):
        """Calls the processing functions for singles, doubles, and hubs in that
        order. Dumps alignment data into json database.
        """

        # Single modules
        single_files = glob.glob(self.relaxed_pdbs_dir + '/singles/*.pdb')
        n_singles = len(single_files)
        for i in range(0, n_singles):
            print('Centering single [{}/{}] {}' \
                .format(i+1, n_singles, single_files[i]))
            self.process_single(single_files[i])

        # Double modules
        double_files = glob.glob(self.relaxed_pdbs_dir + '/doubles/*.pdb')
        nDoubles = len(double_files)
        for i in range(0, nDoubles):
            print('Aligning double [{}/{}] {}' \
                .format(i+1, nDoubles, double_files[i]))
            self.process_double(double_files[i])

        # Hub modules
        hub_files = glob.glob(self.relaxed_pdbs_dir + '/hubs/*.pdb')
        nHubs = len(hub_files)
        for i in range(0, nHubs):
            print('Aligning hub [{}/{}] {}' \
                .format(i+1, nHubs, hub_files[i]))
            self.process_hub(hub_files[i])

        self.n_to_c_tx += self.hub_tx

        print('Total: {} singles, {} doubles, {} hubs'.format(n_singles, nDoubles, nHubs))

        self.dump_xdb()

if __name__ =='__main__':
    safe_exec(main)
