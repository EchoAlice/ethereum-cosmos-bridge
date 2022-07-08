# from time import ctime
from constants import CURRENT_SYNC_COMMITTEE_INDEX, NEXT_SYNC_COMMITTEE_INDEX, SLOTS_PER_EPOCH
from containers import BeaconBlockHeader, LightClientStore, LightClientUpdate, SyncAggregate, SyncCommittee
from merkletreelogic import is_valid_merkle_branch 
from remerkleable.core import View
from specfunctions import validate_light_client_update
import requests

# ctime()

# A first milestone for a light client implementation is to HAVE A LIGHT CLIENT THAT SIMPLY TRACKS THE LATEST STATE/BLOCK ROOT.
def calls_api(url):
  response = requests.get(url)
  json_object = response.json() 
  return json_object

def parse_hex_to_bit(hex_string):
  int_representation = int(hex_string, 16)
  binary_vector = bin(int_representation) 
  if binary_vector[:2] == '0b':
    binary_vector = binary_vector[2:]
  return binary_vector 

def parse_hex_to_byte(hex_string):
  if hex_string[:2] == '0x':
    hex_string = hex_string[2:]
  byte_string = bytes.fromhex(hex_string)
  return byte_string 

def parse_list(list):
  for i in range(len(list)):
    list[i] = parse_hex_to_byte(list[i])

def get_sync_period(slot_number):
  sync_period = slot_number // 8192
  return sync_period

def get_epoch(slot_number):
  epoch = slot_number // SLOTS_PER_EPOCH 
  return epoch

if __name__ == "__main__":
  #                                    
  #                                     \\\\\\\\\\\\\\\\\\\ || ////////////////////
  #                                      \\\\\\\\\\\\\\\\\\\  ////////////////////
  #                                      =========================================
  #                                      INITIALIZATION/BOOTSTRAPPING TO A PERIOD:
  #                                      =========================================
  #                                      ///////////////////  \\\\\\\\\\\\\\\\\\\\
  #                                     /////////////////// || \\\\\\\\\\\\\\\\\\\\
  #
  #     Get block header at slot N in period X = N // 16384
  #     Ask node for current sync committee + proof of checkpoint root
  #     Node responds with a snapshot
  #     
  #     Snapshot contains:
  #     A. Header- Block's header corresponding to the checkpoint root
  #     
  #           The light client stores a header so it can ask for merkle branches to 
  #           authenticate transactions and state against the header
  #
  #     B. Current sync committee- Public Keys and the aggregated pub key of the current sync committee
  #   
  #           The purpose of the sync committee is to allow light clients to keep track
  #           of the chain of beacon block headers. 
  #           Sync committees are (i) updated infrequently, and (ii) saved directly in the beacon state, 
  #           allowing light clients to verify the sync committee with a Merkle branch from a 
  #           block header that they already know about, and use the public keys 
  #           in the sync committee to directly authenticate signatures of more recent blocks.
  #   
  #     C. Current sync committee branch- Proof of the current sync committee in the form of a Merkle branch 


  # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
  # ===================================================================
  # STEP 1:  Gather snapshot from node based on finality 
  #           checkpoint and place data into containers
  # ===================================================================
  # ///////////////////////////////////////////////////////////////////

  # ------------------------------------------
  # MAKE API CALLS FOR CHECKPOINT AND SNAPSHOT
  # ------------------------------------------

  #  ==========
  #  CHECKPOINT
  #  ==========
  # checkpoint_url = "https://lodestar-mainnet.chainsafe.io/eth/v1/beacon/states/finalized/finality_checkpoints"
  # checkpoint = calls_api(checkpoint_url)
  # finalized_checkpoint_root = checkpoint['data']['finalized']['root']  
  
  #  =========
  #  BOOTSTRAP
  #  =========
  bootstrap_url = "https://lodestar-mainnet.chainsafe.io/eth/v1/light_client/bootstrap/0x64f23b5e736a96299d25dc1c1f271b0ce4d666fd9a43f7a0227d16b9d6aed038" 
  bootstrap = calls_api(bootstrap_url)
  
  #  Block Header Data
  bootstrap_header = bootstrap['data']['header']
  
  bootstrap_slot = int(bootstrap_header['slot'])
  bootstrap_proposer_index = int(bootstrap_header['proposer_index'])
  bootstrap_parent_root = bootstrap_header['parent_root']
  bootstrap_state_root = bootstrap_header['state_root']
  bootstrap_body_root = bootstrap_header['body_root']

  #  Sync Committee Data
  list_of_keys = bootstrap['data']['current_sync_committee']['pubkeys']
  current_aggregate_pubkey = bootstrap['data']['current_sync_committee']['aggregate_pubkey']
  current_sync_committee_branch = bootstrap['data']['current_sync_committee_branch']
  
  # ---------------------------------------------------------
  # PARSE JSON INFORMATION ON BLOCK_HEADER AND SYNC_COMMITTEE
  # ---------------------------------------------------------

  #       Aggregate Key and Header Roots
  current_aggregate_pubkey = parse_hex_to_byte(current_aggregate_pubkey)
  bootstrap_parent_root = parse_hex_to_byte(bootstrap_parent_root)
  bootstrap_state_root = parse_hex_to_byte(bootstrap_state_root)
  bootstrap_body_root = parse_hex_to_byte(bootstrap_body_root)

  #       List of Keys
  parse_list(list_of_keys) 
  
  #       Sync Committee Branch 
  parse_list(current_sync_committee_branch) 

  # ------------------------------------------------------
  # CREATE CURRENT BLOCK_HEADER AND SYNC COMMITTEE OBJECTS
  # ------------------------------------------------------
  current_block_header =  BeaconBlockHeader(
    slot = bootstrap_slot, 
    proposer_index = bootstrap_proposer_index, 
    parent_root = bootstrap_parent_root,
    state_root = bootstrap_state_root,
    body_root = bootstrap_body_root
  )

  current_sync_committee = SyncCommittee(
    pubkeys = list_of_keys,
    aggregate_pubkey = current_aggregate_pubkey
  )



  # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
  # =================================================
  # STEP 2: Verify Merkle branch from sync committee
  # =================================================
  # /////////////////////////////////////////////////

  # ---------------------------------------------------------
  #                MERKLEIZE THE OBJECTS
  #
  #   Converts the sync committee object into a merkle root.
  # 
  #   If the state root derived from the sync_committee_root 
  #   combined with its proof branch matches the 
  #   header_state_root AND the block header root with this
  #   state root matches the checkpoint root, you know you're
  #   following the right sync committee.
  # ----------------------------------------------------------

  current_header_root =  View.hash_tree_root(current_block_header)
  current_committee_root = View.hash_tree_root(current_sync_committee) 
  # print("Current sync_committee_root: ")
  # print(sync_committee_root)

  # -----------------------------------
  # HASH NODE AGAINST THE MERKLE BRANCH
  # -----------------------------------

  #  Makes sure the current sync committee hashed against the branch is equivalent to the header state root.
  #  However, all of this information was given to us from the same server.  Hash the information given to us 
  #  (each attribute in BeaconBlockHeader(Container)) against the trusted, finalized checkpoint root to make sure
  #  server serving the bootstrap information for a specified checkpoint root wasn't lying.
  
  assert is_valid_merkle_branch(current_committee_root, 
                                current_sync_committee_branch, 
                                CURRENT_SYNC_COMMITTEE_INDEX, 
                                bootstrap_state_root) 
  
  # assert block_header_root == finalized_checkpoint_root   #  <--- Don't think this works right now. Need the bootstrap  
  #                                                                 api call to contain variable checkpoint 

  # print("Header state root: " + str(header_state_root)) 
  # checkpoint_in_question = '0x229f88ef9dad77baa53dc507ae23a60261968b54aebbe7875144cdf2e7c548d8'
  # checkpoint_in_question = parse_hex_to_byte(checkpoint_in_question)     # finalized_checkpoint_root
  
  # print("block_header_root: ") 
  # print(block_header_root)
  # print(checkpoint_in_question)
  # print("Tahhhh daaaahh") 




  #                                  \\\\\\\\\\\\\\\\\\\   |||   ////////////////////
  #                                   \\\\\\\\\\\\\\\\\\\   |   ////////////////////
  #                                   ==============================================
  #                                   GET COMMITTEE UPDATES UP UNTIL CURRENT PERIOD:
  #                                   ==============================================
  #                                   ///////////////////   |   \\\\\\\\\\\\\\\\\\\\
  #                                  ///////////////////   |||   \\\\\\\\\\\\\\\\\\\\


  # "The light client stores the snapshot and fetches committee updates until it reaches the latest sync period."
  # 
  # Get sycn period updates from current sync period to latest sync period
  
  
  # ////////////////////////////////////
  # ====================================
  # TURN DATA FROM UPDATE INTO VARIABLES
  # ====================================
  # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

  # Should I be getting the update for the period AFTER the bootstrap period or for the CURRENT period? 
  bootstrap_sync_period = get_sync_period(bootstrap_slot)   #  505
  committee_updates_url = "https://lodestar-mainnet.chainsafe.io/eth/v1/light_client/updates?start_period=512&count=1" 
  committee_updates = calls_api(committee_updates_url)
  
  # ================================ 
  # ATTESTED BLOCK HEADER VARIABLES!
  # ================================ 
  attested_header = committee_updates['data'][0]['attested_header']
  
  attested_header_slot_number = int(attested_header['slot'])
  attested_header_proposer_index = int(attested_header['proposer_index'])
  attested_header_parent_root =  attested_header['parent_root']
  attested_header_state_root =  attested_header['state_root']
  attested_header_body_root =  attested_header['body_root']
  
  # From hex to bytes
  attested_header_parent_root = parse_hex_to_byte(attested_header_parent_root)
  attested_header_state_root = parse_hex_to_byte(attested_header_state_root)
  attested_header_body_root = parse_hex_to_byte(attested_header_body_root)

  # ================================= 
  # UPDATES SYNC COMMITTEE VARIABLES!
  # =================================
  next_sync_committee = committee_updates['data'][0]['next_sync_committee']
  updates_list_of_keys = next_sync_committee['pubkeys']
  updates_aggregate_pubkey = next_sync_committee['aggregate_pubkey']

  # From hex to bytes
  parse_list(updates_list_of_keys)
  updates_aggregate_pubkey = parse_hex_to_byte(updates_aggregate_pubkey)

  # ==========================
  # FINALIZED BLOCK VARIABLES!
  # ========================== 
  finalized_header =  committee_updates['data'][0]['finalized_header']
  
  finalized_updates_slot_number = int(finalized_header['slot'])
  finalized_updates_proposer_index = int(finalized_header['proposer_index'])
  finalized_updates_parent_root =  finalized_header['parent_root']
  finalized_updates_state_root =  finalized_header['state_root']
  finalized_updates_body_root =  finalized_header['body_root']
  
  # !!!!!!!! IMPORTANT BLOCK VALUES !!!!!!! 
  print("attested header slot: " + str(attested_header_slot_number)) 
  print("finalized header slot: " + str(finalized_updates_slot_number)) 
  print("bootstrap header slot: " + str(bootstrap_slot)) 
  print('\n') 
  # 511  finalized header slot =  4189312          512 finalized header slot = 4198752 
  print("Final header 512 - 511: " + str(4198752 - 4189312)) 
  print("Finalized block's epoch: " + str(get_epoch(finalized_updates_slot_number)))
  print("Attested block's epoch: " + str(get_epoch(attested_header_slot_number)))

  # From hex to bytes
  finalized_updates_parent_root = parse_hex_to_byte(finalized_updates_parent_root)
  finalized_updates_state_root = parse_hex_to_byte(finalized_updates_state_root)
  finalized_updates_body_root = parse_hex_to_byte(finalized_updates_body_root)

  # ============================================== 
  # Next Sync Committee Branch - from hex to bytes 
  # ============================================== 
  next_sync_committee_branch = committee_updates['data'][0]['next_sync_committee_branch']
  parse_list(next_sync_committee_branch)


  # =================================================== 
  # Finalized Sync Committee Branch - from hex to bytes 
  # =================================================== 
  finalized_updates_branch = committee_updates['data'][0]['finality_branch']
  parse_list(finalized_updates_branch) 
  
  # =========================                  
  # SYNC AGGREGATE VARIABLES!                    
  # ========================= 
  sync_aggregate = committee_updates['data'][0]['sync_aggregate']
  sync_committee_hex = sync_aggregate['sync_committee_bits']
  sync_committee_signature = sync_aggregate['sync_committee_signature']
  
  # From hex to bytes (and bits)
  sync_committee_bits = parse_hex_to_bit(sync_committee_hex) 
  sync_committee_signature = parse_hex_to_byte(sync_committee_signature)

  # ============                  
  # FORK_VERSION                    
  # ============ 
  fork_version =  committee_updates['data'][0]['fork_version']
  # From hex to bytes
  fork_version = parse_hex_to_byte(fork_version)



  # ///////////////////////////////////////////////
  # ----------------------------------------------
  # CREATE COMMITTEE UPDATES OBJECTS AND MERKLEIZE
  # ----------------------------------------------
  # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

  attested_block_header =  BeaconBlockHeader(
    slot = attested_header_slot_number, 
    proposer_index = attested_header_proposer_index, 
    parent_root = attested_header_parent_root,
    state_root = attested_header_state_root,
    body_root = attested_header_body_root 
  )
  
  next_sync_committee = SyncCommittee(
    pubkeys = updates_list_of_keys,
    aggregate_pubkey = updates_aggregate_pubkey
  )

  finalized_block_header =  BeaconBlockHeader(
    slot = finalized_updates_slot_number, 
    proposer_index = finalized_updates_proposer_index, 
    parent_root = finalized_updates_parent_root,
    state_root = finalized_updates_state_root,
    body_root = finalized_updates_body_root 
  )

  sync_aggregate = SyncAggregate(
    sync_committee_bits = sync_committee_bits, 
    sync_committee_signature = sync_committee_signature 
  )

  attested_block_header_root =  View.hash_tree_root(attested_block_header)
  next_sync_committee_root = View.hash_tree_root(next_sync_committee) 
  finalized_block_header_root =  View.hash_tree_root(finalized_block_header)
  sync_aggregate_root =  View.hash_tree_root(sync_aggregate)
  
  # Next sync committee hashed against proof and compared to finalized state root
  assert is_valid_merkle_branch(next_sync_committee_root, 
                                next_sync_committee_branch, 
                                NEXT_SYNC_COMMITTEE_INDEX, 
                                finalized_updates_state_root) 



  # //////////////////////////////////////////////////////////////
  # -------------------------------------------------------------
  # PLACE OBJECTS INTO LIGHT CLIENT STORE AND LIGHT CLIENT UPDATE 
  # -------------------------------------------------------------
  # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\/\\\\\\\\\\\
   
  # ===================                                   IMPORTANT QUESTION:
  #  LIGHT CLIENT STORE        How do I tie the finalized block header back to the bootstrap checkpoint root?
  # ===================        Because right now there's a gap in the logic:  
  #                                 Yes the next sync committee hashes against merkle proof to equal the finalized state,
  #                                 but the finalized state isn't connected back to the checkpoint root.
  #                                               print(finalized_block_header_root)
  # 
  # 
  #                            For now, press on and execute spec functions properly

  #  I think I need to store the information from the bootstrap call into here.  not update stuff...
  light_client_store =  LightClientStore(
    finalized_header = finalized_block_header, 
    current_sync_committee = current_sync_committee, 
    next_sync_committee = next_sync_committee,

    #                              Figure out what these values are 
    # best_valid_update = ,
    # optimistic_header = ,
    # previous_max_active_participants = ,
    # current_max_active_participants = 
  )

  # ====================
  #  LIGHT CLIENT UPDATE 
  # ====================

  light_client_update = LightClientUpdate(
    attested_header = attested_block_header,
    next_sync_committee = next_sync_committee,
    next_sync_committee_branch = next_sync_committee_branch,
    finalized_header = finalized_block_header,
    finality_branch = finalized_updates_branch,
    # A record of which validators in the current sync committee voted for the chain head in the previous slot
    #
    # Contains the sync committee's bitfield and signature required for verifying the attested header
    sync_aggregate = sync_aggregate,
    # Slot at which the aggregate signature was created (untrusted)    I don't know this value
    signature_slot =  attested_header_slot_number - 1 
  )

  # validate_light_client_update(light_client_store,
  #                             light_client_update,
  #                             ) 
  # print(committee_updates) 



# update.signature_slot > active_header.slot

  # print(light_client_store) 
  # print(light_client_update)


  # ///////////////////////////////////////////////
  # ----------------------------------------------
  #            BRING IN THE MVP SPEC!! 
  # ----------------------------------------------
  # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\



  # print(attested_header_slot_number - finalized_updates_slot_number)
  # print((bootstrap_slot - finalized_updates_slot_number)/32)  














  #                                   \\\\\\\\\\\\\\\\\\\ || ////////////////////
  #                                    \\\\\\\\\\\\\\\\\\\  ////////////////////
  #                                    ========================================
  #                                            SYNC TO THE LATEST BLOCK:
  #                                    ========================================
  #                                    ///////////////////  \\\\\\\\\\\\\\\\\\\\
  #                                   /////////////////// || \\\\\\\\\\\\\\\\\\\\