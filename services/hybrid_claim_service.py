import os
import subprocess
import json
from models.user import User, db

class HybridClaimService:
    """
    Hybrid claim service that uses JavaScript subprocess for contract interactions
    while keeping database operations in Python.
    """
    
    def __init__(self, scripts_dir=None):
        """
        Initialize the hybrid claim service.
        
        Args:
            scripts_dir (str): Directory containing JavaScript scripts (default: scripts/)
        """
        if scripts_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.scripts_dir = os.path.join(os.path.dirname(current_dir), 'scripts')
        else:
            self.scripts_dir = scripts_dir
    
    def add_claim(self, investor_user_id, trusted_issuer_user_id, topic, data):
        """
        Add a claim using the hybrid approach (Python database + JavaScript contracts).
        
        Args:
            investor_user_id (int): ID of the investor user
            trusted_issuer_user_id (int): ID of the trusted issuer user
            topic (int): Claim topic
            data (str): Claim data
            
        Returns:
            dict: Result of adding claim
        """
        try:
            print(f"🧪 HYBRID CLAIM ADDITION")
            print(f"🔍 Investor User ID: {investor_user_id}")
            print(f"🔍 Trusted Issuer User ID: {trusted_issuer_user_id}")
            print(f"🔍 Topic: {topic}")
            print(f"🔍 Data: {data}")
            
            # STEP 1: Load data from database
            print("📋 STEP 1: Loading data from database...")
            
            # Find investor
            investor = User.query.get(investor_user_id)
            if not investor:
                return {'success': False, 'error': f'Investor user {investor_user_id} not found'}
            
            print(f"✅ Found investor: {investor.username}")
            print(f"   Wallet: {investor.wallet_address}")
            print(f"   OnchainID: {investor.onchain_id}")
            
            # Find trusted issuer
            trusted_issuer = User.query.get(trusted_issuer_user_id)
            if not trusted_issuer:
                return {'success': False, 'error': f'Trusted issuer user {trusted_issuer_user_id} not found'}
            
            print(f"✅ Found trusted issuer: {trusted_issuer.username}")
            print(f"   Wallet: {trusted_issuer.wallet_address}")
            print(f"   ClaimIssuer: {trusted_issuer.claim_issuer_address}")
            
            # Validate required data
            if not investor.onchain_id:
                return {'success': False, 'error': f'Investor {investor.username} has no OnchainID'}
            
            if not trusted_issuer.claim_issuer_address:
                return {'success': False, 'error': f'Trusted issuer {trusted_issuer.username} has no ClaimIssuer contract'}
            
            # STEP 2: Pre-index the ClaimIssuer management key that will be added
            print("🔑 STEP 2: Pre-indexing ClaimIssuer management key...")
            try:
                from services.transaction_indexer import TransactionIndexer
                from services.web3_service import Web3Service
                
                web3_service = Web3Service()
                transaction_indexer = TransactionIndexer(web3_service)
                
                # Pre-index the ClaimIssuer as management key to investor's OnchainID
                key_id = transaction_indexer.pre_index_onchainid_key(
                    onchainid_address=investor.onchain_id,
                    wallet_address=trusted_issuer.claim_issuer_address,  # ClaimIssuer contract address
                    key_type='management',
                    owner_type='trusted_issuer',
                    owner_id=trusted_issuer_user_id
                )
                
                if key_id:
                    print(f"✅ Pre-indexed ClaimIssuer management key: {trusted_issuer.claim_issuer_address} -> {investor.onchain_id}")
                else:
                    print(f"⚠️ Failed to pre-index ClaimIssuer management key")
                    
            except Exception as e:
                print(f"⚠️ Error pre-indexing ClaimIssuer management key: {e}")
            
            # STEP 3: Call JavaScript subprocess to add claim
            print("🚀 STEP 3: Calling JavaScript subprocess to add claim...")
            
            # Create configuration for JavaScript
            config = {
                "investorOnchainID": investor.onchain_id,
                "trustedIssuerAddress": trusted_issuer.wallet_address,
                "claimIssuerAddress": trusted_issuer.claim_issuer_address,
                "trustedIssuerPrivateKey": trusted_issuer.private_key,  # Add private key for signing
                "topic": topic,
                "claimData": data
            }
            
            # Create temporary config file in scripts directory
            config_file = os.path.join(self.scripts_dir, 'claim_config.json')
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"🔧 Created config file: {config_file}")
            print(f"🔧 Configuration:")
            print(f"   investorOnchainID: {investor.onchain_id}")
            print(f"   trustedIssuerAddress: {trusted_issuer.wallet_address}")
            print(f"   claimIssuerAddress: {trusted_issuer.claim_issuer_address}")
            print(f"   topic: {topic}")
            print(f"   claimData: {data}")
            print(f"   scheme: 1 (ECDSA) - hardcoded")
            print(f"   uri: '' - hardcoded")
            
            # Prepare command
            cmd = [
                "npx", "hardhat", "run", "addClaim.js",
                "--network", "localhost"
            ]
            
            print(f"🔧 Running command: {' '.join(cmd)}")
            
            # Run the JavaScript subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.scripts_dir
            )
            
            print(f"📤 JavaScript output:")
            print(result.stdout)
            
            if result.stderr:
                print(f"⚠️ JavaScript errors:")
                print(result.stderr)
            
            # Check if the command was successful
            if result.returncode == 0:
                print("✅ JavaScript subprocess completed successfully!")
                
                # Parse the JSON result
                js_result = self._parse_js_result(result.stdout)
                
                if js_result and js_result.get('success'):
                    print("🎉 Claim addition successful!")
                    
                    # Update the pre-indexed ClaimIssuer management key with transaction hash
                    try:
                        from services.transaction_indexer import TransactionIndexer
                        from services.web3_service import Web3Service
                        
                        web3_service = Web3Service()
                        transaction_indexer = TransactionIndexer(web3_service)
                        
                        # Get the actual key hash from the ClaimIssuer address
                        key_hash = web3_service.w3.keccak(web3_service.w3.codec.encode(['address'], [trusted_issuer.claim_issuer_address])).hex()
                        
                        # Find and update the pre-indexed key
                        pending_keys = transaction_indexer.get_pending_onchainid_keys(investor.onchain_id)
                        for key in pending_keys:
                            if (key.wallet_address == trusted_issuer.claim_issuer_address and 
                                key.key_type == 'management'):
                                
                                transaction_indexer.update_onchainid_key_after_transaction(
                                    key_id=key.id,
                                    transaction_hash=js_result.get('transactionHash'),
                                    actual_key_hash=key_hash
                                )
                                print(f"✅ Updated ClaimIssuer management key with transaction: {js_result.get('transactionHash')}")
                                break
                                
                    except Exception as e:
                        print(f"⚠️ Error updating ClaimIssuer management key: {e}")
                    
                    # Return the result with additional context
                    return {
                        'success': True,
                        'transaction_hash': js_result.get('transactionHash'),
                        'claim_id': js_result.get('claimId'),
                        'claim_data': js_result.get('claim', {}),
                        'message': f'Claim added successfully for topic {topic}',
                        'investor_onchainid': investor.onchain_id,
                        'trusted_issuer': trusted_issuer.wallet_address,
                        'claimissuer': trusted_issuer.claim_issuer_address
                    }
                else:
                    error_msg = js_result.get('error', 'Unknown error') if js_result else 'Failed to parse JavaScript result'
                    return {'success': False, 'error': f'Claim addition failed: {error_msg}'}
                    
            else:
                return {'success': False, 'error': f'JavaScript subprocess failed with return code: {result.returncode}'}
                
        except Exception as e:
            print(f"❌ Error in hybrid claim addition: {e}")
            return {'success': False, 'error': f'Error in hybrid claim addition: {str(e)}'}
            
        finally:
            # Clean up config file
            try:
                if os.path.exists(config_file):
                    os.remove(config_file)
                    print(f"🧹 Cleaned up config file: {config_file}")
            except Exception as e:
                print(f"⚠️ Could not clean up config file: {e}")
    
    def _parse_js_result(self, stdout):
        """
        Parse the JSON result from JavaScript output.
        """
        try:
            lines = stdout.split('\n')
            json_started = False
            json_lines = []
            
            for line in lines:
                if "🎯 RESULT:" in line:
                    json_started = True
                    continue
                if json_started and line.strip():
                    json_lines.append(line)
            
            if json_lines:
                json_output = '\n'.join(json_lines)
                return json.loads(json_output)
            else:
                print("⚠️ Could not find JSON result in JavaScript output")
                return None
                
        except json.JSONDecodeError as e:
            print(f"⚠️ Could not parse JSON result: {e}")
            return None
    
    def add_multiple_claims(self, investor_user_id, trusted_issuer_user_id, claims_list):
        """
        Add multiple claims using the hybrid approach.
        
        Args:
            investor_user_id (int): ID of the investor user
            trusted_issuer_user_id (int): ID of the trusted issuer user
            claims_list (list): List of tuples (topic, data)
        """
        added_claims = []
        failed_claims = []
        
        for topic, data in claims_list:
            print(f"🔧 Processing claim - Topic: {topic}, Data: {data}")
            
            result = self.add_claim(investor_user_id, trusted_issuer_user_id, topic, data)
            
            if result['success']:
                added_claims.append({
                    'topic': topic,
                    'data': data,
                    'transaction_hash': result.get('transaction_hash'),
                    'claim_id': result.get('claim_id')
                })
                print(f"✅ Added claim: Topic {topic}, Data: {data}")
            else:
                failed_claims.append({
                    'topic': topic,
                    'data': data,
                    'error': result.get('error')
                })
                print(f"❌ Failed claim: Topic {topic}, Data: {data} - {result.get('error')}")
        
        return {
            'success': len(failed_claims) == 0,
            'added_claims': added_claims,
            'failed_claims': failed_claims,
            'total_claims': len(claims_list),
            'successful_claims': len(added_claims),
            'failed_claims_count': len(failed_claims)
        } 