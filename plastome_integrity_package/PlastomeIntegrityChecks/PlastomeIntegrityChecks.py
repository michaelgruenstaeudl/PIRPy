import os, subprocess, logging
import xml.etree.ElementTree as ET
import pandas as pd
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.SeqFeature import SeqFeature, FeatureLocation

class Entrez_Interaction:

	def __init__(self, logger = None):
		self.log = logger or logging.getLogger(__name__ + ".Entrez_Interaction")

	def retrieve_uids(self, query, min_date = None):
		'''
		Retrieves and returns a list of UIDs that are the result of an Entrez query
		Params:
		 - query: the Entrez query
		 - min_date: date. the minimum data to start searching from.
		'''
		if min_date:
			esearch_args = ['esearch', '-db', 'nucleotide', '-sort', '"Date Released"', '-mindate', min_date.strftime("%Y/%m/%d"), '-maxdate', date.today().strftime("%Y/%m/%d"), '-query', query]
		else:
			esearch_args = ['esearch', '-db', 'nucleotide', '-sort', '"Date Released"', '-query', query]
		esearch = subprocess.Popen(esearch_args, stdout=subprocess.PIPE)
		efetchargs = ["efetch", "-db", "nucleotide", "-format", "uid"]
		efetch = subprocess.Popen(efetchargs, stdin=esearch.stdout, stdout=subprocess.PIPE)
		out, err = efetch.communicate()
		
		return list(map(int, out.splitlines()))[::-1]

	def fetch_xml_entry(self, uid):
		'''
		Fetches one GenBank entry in GenBank XML format and returns it as ElementTree
		Params:
		 - uid: the UID of the GenBank entry
		Returns: ElementTree of entry
		'''
		self.log.debug("Fetching XML GenBank entry " + str(uid))
		esummaryargs = ["esummary", "-db", "nucleotide", "-format", "gb", "-mode", "xml", "-id", str(uid)]
		esummary = subprocess.Popen(esummaryargs, stdout=subprocess.PIPE)
		out, err = esummary.communicate()
		return ET.fromstring(out)
	
	def parse_xml_entry(self, entry):
		'''
		Parses a GenBank XML entry and returns a dictionary of field name/value pairs
		Params:
		 - entry: ElementTree. The XML entry		 
		'''
		# Parse out the relevant info from XML-formatted record summary
		uid_data = entry.find("GBSeq")
		fields = {}
		accession = uid_data.find("GBSeq_primary-accession").text
		fields["ACCESSION"] = accession
		fields["VERSION"] = uid_data.find("GBSeq_accession-version").text.split('.')[1]
		fields["ORGANISM"] = uid_data.find("GBSeq_organism").text
		fields["SEQ_LEN"] = uid_data.find("GBSeq_length").text
		fields["TAXONOMY"] = uid_data.find("GBSeq_taxonomy").text

		# Parse and format the date that the record was first online
		month_map = {"JAN":"01", "FEB":"02", "MAR":"03", "APR":"04", "MAY":"05", "JUN":"06", "JUL":"07", "AUG":"08", "SEP":"09", "OCT":"10", "NOV":"11", "DEC":"12"}
		create_date = uid_data.find("GBSeq_create-date").text.split('-')
		fields["CREATE_DATE"] = create_date[2] + "-" + month_map[create_date[1]] + "-" + create_date[0]

		# Parse all info related to the authors and the publication
		references = uid_data.find("GBSeq_references").findall("GBReference")
		authstring = ""
		title = ""
		citation = ""

		# Properly format the author output
		for ref in references:
			# Look for a reference that has authors (not all entries have a reference with authors)
			authors = ref.find("GBReference_authors")
			if authors:
				title = ref.find("GBReference_title").text
				citation = ref.find("GBReference_journal").text
				authors = ref.find("GBReference_authors").findall("GBAuthor")
				for author in authors:
					authstring = authstring + author.text + ","
				authstring = authstring[:-2]
				break
		fields["AUTHORS"] = authstring
		fields["TITLE"] = title
		fields["REFERENCE"] = citation

		# Parse comment field for RefSeq
		note = ""
		duplseq = None
		if accession[:3] == "NC_":
			comments = uid_data.find("GBSeq_comment").text
			for comment in comments.split(";"):
				keyw1 = "PROVISIONAL REFSEQ: This record has not yet been subject to final NCBI review"
				keyw2 = "The reference sequence is identical to"
				if keyw1 in comment or keyw2 in comment:
					duplseq = comment.split(" ")[-1][:-1]
					note = "The REFSEQ accession '%s' is identical to accession '%s'." % (accession, duplseq)
		fields["NOTE"] = note
		fields["DUPLSEQ"] = duplseq

		return fields

	def fetch_gb_entry(self, acc_id, outdir):
		'''
		Saves GenBank flatfile with accession number "acc_id" to
		outdir and returns the path and filename of the file
		Params:
		 - acc_id: accession number of the GenBank entry
		 - outdir: file path to output directory
		'''
		self.log.debug("Fetching GenBank entry %s and saving to %s" % (str(acc_id), outdir))
		gbFile = os.path.join(outdir, str(acc_id) + ".gb")
		with open(gbFile, "w") as outfile:
			efetchargs = ["efetch", "-db", "nucleotide", "-format", "gb", "-id", str(acc_id)]
			efetch = subprocess.Popen(efetchargs, stdout=outfile)
			efetch.wait()
		if not os.path.isfile(gbFile):
			raise Exception("Error retrieving GenBank flatfile of accession " + str(acc_id))
		elif os.path.getsize(gbFile) == 0:
			raise Exception("Error retrieving GenBank flatfile of accession " + str(acc_id))
		return gbFile
		
		
class IR_Operations:
	
	def __init__(self, logger = None):
		self.log = logger or logging.getLogger(__name__ + ".IR_Operations")

	###############
	# I/O methods #
	###############

	def read_record(self, fp_record):
		'''
		Reads a GenBank flat file and returns it as SeqRecord
		'''
		rec = None
		if os.path.isfile(fp_record):
			accession = os.path.splitext(fp_record)[0]
			try:			
				rec = SeqIO.read(fp_record, "genbank")
			except Exception as err:
				raise Exception("Error reading record of accession `%s`: %s. Skipping this accession." % (str(accession), str(err)))			
		else:
			raise Exception("Error reading record: Unable to find '%s'." % (fp_record))
		return rec
			
	def write_sequence_to_fasta(self, seq, header, fp_outfile):
		'''
		Writes a sequence to a new file in FASTA format
		Params:
		 - seq: the sequence
		 - header: string that will be written as header in the FASTA file
		 - fp_outfile: file path to output file
		'''
		if not seq is None:
			if not header.startswith(">"):
				header = ">" + header				
			with open(fp_outfile, "w") as fh_outfile:
				fh_outfile.write(header + "\n")
				fh_outfile.write(seq + "\n")
				
	def write_irs_to_fasta(self, rec, IRa, IRb, fp_outdir, rev_comp = False):
		'''
		Writes the inverted repeat SeqFeatures' sequences to separate files in FASTA format
		Params:
		 - rec: the SeqRecord from which the SeqFeature's sequences will be extracted
		 - IRa: SeqFeature that corresponds to inverted repeat A
		 - IRb: SeqFeature that corresponds to inverted repeat B
		 - fp_outdir: file path to output directory
		 - rev_comp: Boolean. Indicates whether the reverse complement of IRb's sequence will be written instead of as provided
		'''
		accession = str(rec.id).split('.')[0]
		if not (IRa is None or IRb is None):
			IRa_seq = str(IRa.extract(rec).seq)
			IRa_header = str(accession) + "_IRa"	
			IRb_header = str(accession) + "_IRb_revComp"
			if rev_comp:
				IRb_seq = str(IRb.extract(rec).seq.reverse_complement())				
			else:
				IRb_seq = str(IRb.extract(rec).seq)				
				
			self.write_sequence_to_fasta(IRa_seq, IRa_header, os.path.join(fp_outdir, accession + "_IRa.fasta"))	
			self.write_sequence_to_fasta(IRb_seq, IRb_header, os.path.join(fp_outdir, accession + "_IRb_revComp.fasta"))
		elif not IRa is None and IRb is None:
			IRa_seq = str(IRa.extract(rec).seq)
			IRa_header = str(accession) + "_IRa"
			self.write_sequence_to_fasta(IRa_seq, IRa_header, os.path.join(fp_outdir, accession + "_IRa.fasta"))
		elif IRa is None and not IRb is None:
			IRb_header = str(accession) + "_IRb_revComp"
			if rev_comp:
				IRb_seq = str(IRb.extract(rec).seq.reverse_complement())				
			else:
				IRb_seq = str(IRb.extract(rec).seq)			
			self.write_sequence_to_fasta(IRb_seq, IRb_header, os.path.join(fp_outdir, accession + "_IRb_revComp.fasta"))

	##################################
	# feature identification methods #
	##################################

	def identify_junction(self, feature, rec_len):
		'''
		Evaluates if a feature is a junction between an inverted repeat and a single copy region,
		and returns the appropriate junction type as an integer.
		The function checks for hard identifiers first, then tries to infer the type through soft identifiers
		Params:
		 - feature: the SeqFeature
		 - rec_len: length of the SeqRecord
		Return values:
		-1: Feature cannot be identified as junction
		0:  Feature is identified as JLB (junction LSC -> IRb)
		1:  Feature is identified as JSB (junction IRb -> SSC)
		2:  Feature is identified as JSA (junction SSC -> IRa)
		3:  Feature is  identified as JLA (junction IRa -> LSC)
		4:  Ambiguous (more than one possible junction type found)
		'''
		junction_type = None

		if len(feature) < 3:
			identified = False
			possible_junctions = []

			jlb_identifiers = {"hard": ["jlb", "lsc-irb", "irb-lsc"], "soft": ["lsc-ir", "ir-lsc"]}
			jsb_identifiers = {"hard": ["jsb", "ssc-irb", "irb-ssc"], "soft": ["ssc-ir", "ir-ssc"]}
			jsa_identifiers = {"hard": ["jsa", "ssc-ira", "ira-ssc"], "soft": ["ssc-ir", "ir-ssc"]}
			jla_identifiers = {"hard": ["jla", "ira-lsc", "lsc-ira"], "soft": ["lsc-ir", "ir-lsc"]}

			# TODO: implement a check that looks at feature.qualifiers["standard_name"] for values ["jlb", "jsb", "jsa", "jla"]

			if any(identifier in feature.qualifiers["note"][0].lower() for identifier in jlb_identifiers["hard"]):
				junction_type = 0
				identified = True
			elif any(identifier in feature.qualifiers["note"][0].lower() for identifier in jlb_identifiers["soft"]):
				possible_junctions.append(0)

			if not identified:
				if any(identifier in feature.qualifiers["note"][0].lower() for identifier in jsb_identifiers["hard"]):
					junction_type = 1
					identified = True
				elif any(identifier in feature.qualifiers["note"][0].lower() for identifier in jsb_identifiers["soft"]):
					possible_junctions.append(1)

			if not identified:
				if any(identifier in feature.qualifiers["note"][0].lower() for identifier in jsa_identifiers["hard"]):
					junction_type = 2
					identified = True
				elif any(identifier in feature.qualifiers["note"][0].lower() for identifier in jsa_identifiers["soft"]):
					possible_junctions.append(2)

			if not identified:
				if any(identifier in feature.qualifiers["note"][0].lower() for identifier in jla_identifiers["hard"]):
					junction_type = 3
					identified = True
				elif any(identifier in feature.qualifiers["note"][0].lower() for identifier in jla_identifiers["soft"]):
					possible_junctions.append(3)

			if not identified:
				if len(possible_junctions) == 1:
					junction_type = possible_junctions[0]
				elif len(possible_junctions) > 1:
					junction_type = 4
					# if the feature is located at the end of the sequence, it is most certainly a JLA
					# NOTE: found exceptions to this rule -> TODO: account for those exceptions
					if 3 in possible_junctions:
						if feature.location.start in range(rec_len - 10, rec_len):
							identified = True
							junction_type = 3
						else:
							# if there is only one other junction type in consideration, pick it
							if len(possible_junctions) == 2:
								identified = True
								junction_type = possible_junctions[0]
				else:
					junction_type = -1
		else:
			junction_type = -1
		return junction_type

	def infer_irs_from_junctions(self, rec_len, all_misc_features):
		'''
		Tries to infer the IR positions from the information provided by the junction features;
		returns the IRs as full features.
		Params:
		 - rec_len: length of the SeqRecord
		 - all_misc_features: list of "misc_feature" SeqFeatures
		'''
		IRa = None
		IRb = None
		jlb_feat = None
		jsb_feat = None
		jsa_feat = None
		jla_feat = None
		
		i = 0
		for misc_feature in [mf for mf in all_misc_features if "note" in mf.qualifiers]:
			i += 1
			self.log.debug("Checking misc_feature %s out of %s (position %s - %s)..." % \
			  (str(i), str(len(all_misc_features)), str(misc_feature.location.start), str(misc_feature.location.end)))
			junction_type = self.identify_junction(misc_feature, rec_len)
			if junction_type == 0: # JLB
				self.log.debug("Found junction LSC-IRb.")
				jlb_feat = misc_feature
			elif junction_type == 1: # JSB
				self.log.debug("Found junction IRb-SSC.")
				jsb_feat = misc_feature
			elif junction_type == 2: # JSA
				self.log.debug("Found junction SSC-IRa.")
				jsa_feat = misc_feature
			elif junction_type == 3: # JLA
				self.log.debug("Found junction IRa-LSC")
				jla_feat = misc_feature
			elif junction_type == 4: # Ambiguous
				self.log.debug("Found a junction but its identifiers are ambiguous.")		

		for junction in [jlb_feat, jsb_feat, jsa_feat, jla_feat]:
			junction = self.adjust_feature_location(junction)
		if jlb_feat and jsb_feat:
			self.log.debug("Constructing IRb from found junctions.")
			if jlb_feat.location.start < jsb_feat.location.start:
				IRb = SeqFeature(FeatureLocation(jlb_feat.location.end-1, jsb_feat.location.start+1, strand = 1))
			else:
				IRb = SeqFeature(FeatureLocation(jsb_feat.location.end-1, jlb_feat.location.start+1, strand = 1))
		if jsa_feat:
			self.log.debug("Constructing IRa from found junctions.")
			if jla_feat:
				# comparing start locations to see in which order the IRs and SC regions are in the genome
				if jsa_feat.location.start < jla_feat.location.start:
					IRa = SeqFeature(FeatureLocation(jsa_feat.location.end-1, jla_feat.location.start+1, strand = 1))
				else:
					IRa = SeqFeature(FeatureLocation(jla_feat.location.end-1, jsa_feat.location.start+1, strand = 1))
			elif jsb_feat:
				# If JLA is not given, we assume that the plastid genome is split at the JLA
				# (i.e. start of the JLA is the last position in the sequence, end of the JLA is the first position)
				if jsb_feat.location.start < jsa_feat.location.start:
					IRa = SeqFeature(FeatureLocation(jsa_feat.location.end-1, rec_len, strand = 1))
				else:
					IRa = SeqFeature(FeatureLocation(0, jsa_feat.location.start+1, strand = 1))
			else:
				# if JSB is not given either, we assume the plastid genome follows the
				# convention of (start:LSC|IRb|SSC|IRa:end)
				IRa = SeqFeature(FeatureLocation(jsa_feat.location.end-1, rec_len, strand = 1))
		return IRa, IRb

	def infer_irs_from_single_copy_regions(self, rec_len, all_mf_no_pseudo, IRa = None, IRb = None):
		'''
		Tries to infer the IR positions from the information provided by the single copy features;
		returns the IRs as full features
		Params:
		 - rec_len: length of the record
		 - all_mf_no_pseudo: list of "misc_feature" SeqFeatures excluding pseudo features
		 - IRa: SeqFeature that corresponds to Inverted Repeat A
		 - IRb: SeqFeature that corresponds to Inverted Repeat B
		'''
		ssc = None
		lsc = None
		ssc_identifiers = ["ssc", "small single copy"]
		lsc_identifiers = ["lsc", "large single copy"]
		blacklist = ["jlb", "jsb", "jsa", "jla", "junction"]		
		i = 0
		for misc_feature in [mf for mf in all_mf_no_pseudo if "note" in mf.qualifiers]:
			i += 1
			self.log.debug("Checking misc_feature %s out of %s (position %s - %s)..." % \
			  (str(i), str(len(all_mf_no_pseudo)), str(misc_feature.location.start), str(misc_feature.location.end)))
			if any(identifier in misc_feature.qualifiers["note"][0].lower() for identifier in ssc_identifiers) and \
			   not any(blocked in misc_feature.qualifiers["note"][0].lower() for blocked in blacklist):
				self.log.debug("Found identifier for SSC")
				ssc = misc_feature
			if any(identifier in misc_feature.qualifiers["note"][0].lower() for identifier in lsc_identifiers) and \
			   not any(blocked in misc_feature.qualifiers["note"][0].lower() for blocked in blacklist):
				self.log.debug("Found identifier for LSC")
				lsc = misc_feature
		if lsc and ssc:
			if lsc.location.start < ssc.location.start:
				ira_start = ssc.location.end - 1
				ira_end = lsc.location.start
				irb_start = lsc.location.end - 1
				irb_end = ssc.location.start
				if ira_end == 0:
					ira_end = rec_len
				if IRa is None:
					self.log.debug("Constructing IRa from found single-copy positions.")
					IRa = SeqFeature(FeatureLocation(ira_start, ira_end), type="misc_feature", strand=1)
				if IRb is None:
					self.log.debug("Constructing IRb from found single-copy positions.")
					IRb = SeqFeature(FeatureLocation(irb_start, irb_end), type="misc_feature", strand=1)
			else:
				ira_start = lsc.location.end - 1
				ira_end = ssc.location.start
				irb_start = ssc.location.end - 1
				irb_end = lsc.location.start
				if irb_end == 0:
					irb_end = rec_len
				if IRa is None:
					self.log.debug("Constructing IRa from found single-copy positions.")
					IRa = SeqFeature(FeatureLocation(lsc.location.end-1, ssc.location.start), type="misc_feature", strand=1)
				if IRb is None:
					self.log.debug("Constructing IRb from found single-copy positions.")
					IRb = SeqFeature(FeatureLocation(ssc.location.end-1, lsc.location.start), type="misc_feature", strand=1)
		return IRa, IRb
	
	def identify_irs_in_misc_features(self, all_mf_no_pseudo, IRa = None, IRb = None):
		'''
		Tries to infer the IR positions from the information provided by the misc_features; returns the IRs as full features
		Params:
		 - all_mf_no_pseudo: list of "misc_feature" SeqFeatures excluding pseudo features
		 - IRa: SeqFeature that corresponds to Inverted Repeat A
		 - IRb: SeqFeature that corresponds to Inverted Repeat B
		'''
		ira_identifiers = ["ira", "inverted repeat a"]
		irb_identifiers = ["irb", "inverted repeat b"]
		blacklist = ["jlb", "jsb", "jsa", "jla", "junction"]
		# STEP 1: Check for hard identifiers
		for misc_feature in [mf for mf in all_mf_no_pseudo if "note" in mf.qualifiers]:
			if IRa is None:
				if any(identifier in misc_feature.qualifiers["note"][0].lower() for identifier in ira_identifiers) and \
				  not any(blocked in misc_feature.qualifiers["note"][0].lower() for blocked in blacklist):
					self.log.debug("Found identifier for IRa: " % str(misc_feature.qualifiers["note"][0]))
					if len(misc_feature) > 100:
						IRa = misc_feature
					else:
						self.log.debug("Feature is too short (%s bp) to be an IR." % str(len(misc_feature)))
			if IRb is None:
				if any(identifier in misc_feature.qualifiers["note"][0].lower() for identifier in irb_identifiers) and \
				  not any(blocked in misc_feature.qualifiers["note"][0].lower() for blocked in blacklist):
					self.log.debug("Found identifier for IRb: %s" % str(misc_feature.qualifiers["note"][0]))
					if len(misc_feature) > 100:
						IRb = misc_feature
					else:
						self.log.debug("Feature is too short (%s bp) to be an IR." % str(len(misc_feature)))
		# STEP 2: Check for soft identifiers
		if IRa is None or IRb is None:
			for misc_feature in [mf for mf in all_mf_no_pseudo if "note" in mf.qualifiers]:
				if (("inverted" in misc_feature.qualifiers["note"][0].lower() and \
				  "repeat" in misc_feature.qualifiers["note"][0].lower()) or \
				  "IR" in misc_feature.qualifiers["note"][0]) and \
				  not any(blocked in misc_feature.qualifiers["note"][0].lower() for blocked in blacklist):
					self.log.debug("Found general identifier for IRs: %s" % str(misc_feature.qualifiers["note"][0]))
					if len(misc_feature) > 100:
						if IRb is None:
							self.log.debug("Assign feature as IRb")
							IRb = misc_feature
						elif IRa is None:
							self.log.debug("Assign feature as IRa")
							IRa = misc_feature
					else:
						self.log.debug("Feature is too short (%s bp) to be an IR." % str(len(misc_feature)))
		return IRa, IRb	
		
	def identify_irs_in_repeat_features(self, all_repeat_features, IRa = None, IRb = None, min_IR_len = 1000):
		'''
		Tries to infer the IR positions from the information provided by the repeat_features; returns the IRs as SeqFeatures
		Params:
		 - all_repeat_features: list of "repeat_feature" SeqFeatures
		 - IRa: SeqFeature that corresponds to Inverted Repeat A
		 - IRb: SeqFeature that corresponds to Inverted Repeat B
		 - min_IR_len: minimum length identified IRs must have.
		'''		
		ira_identifiers = ["ira", "inverted repeat a"]
		irb_identifiers = ["irb", "inverted repeat b"]
		# Loop through repeat_regions and attempt to identify IRs
		self.log.debug("Checking all repeat_features with 'rpt_type' qualifier for IR information...")
		i = 0
		for repeat_feature in [rf for rf in all_repeat_features if "rpt_type" in rf.qualifiers]:
			i += 1
			self.log.debug("Checking repeat_feature %s out of %s (position %s - %s)..." % \
			  (str(i), str(len(all_repeat_features)), str(repeat_feature.location.start), str(repeat_feature.location.end)))
			if repeat_feature.qualifiers["rpt_type"][0].lower() == "inverted":
				self.log.debug("Feature is of rpt_type=inverted")
				if len(repeat_feature) > min_IR_len:
					if "note" in repeat_feature.qualifiers:
						self.log.debug("Checking note qualifier for IR identifiers.")
						# If the "note" qualifier contains explicit mention of which IR (a/b) we are looking at, assign
						# it to the appropriate variable.
						if any(identifier in repeat_feature.qualifiers["note"][0].lower() for identifier in ira_identifiers):
							self.log.debug("Found identifier for IRa.")
							IRa = repeat_feature
						elif any(identifier in repeat_feature.qualifiers["note"][0].lower() for identifier in irb_identifiers):
							self.log.debug("Found identifier for IRb.")
							IRb = repeat_feature
						# If the "note" qualifier holds no information on which IR we are looking at, assign
						# the repeat feature to one of the variables that hasn't been initialized yet. IRb
						# gets assigned first, since it is located before IRa in the sequence, so if there
						# is no further information given, the first IR found is assumed to be IRb.
						elif IRb is None:
							self.log.debug("No specific identifier found. Assigned feature as IRb.")
							IRb = repeat_feature
						# Note: Elif-statement in this context assures that IRa is assigned only if IRb is not None.
						elif IRa is None:
							self.log.debug("No specific identifier found. Assigned feature as IRa.")
							IRa = repeat_feature
					# If the "note" qualifier does not exist, assign the repeat feature to one of the variables
					# that hasn't been initialized yet. IRb gets assigned first, since it is located before IRa
					# in the sequence, so if there is no further information given, the first IR found is assumed to be IRb.
					elif IRb is None:
						self.log.debug("No 'note' qualifier found. Assigned feature as IRb.")
						IRb = repeat_feature
					# Note: Elif-statement in this context assures that IRa is assigned only if IRb is not None.
					elif IRa is None:
						self.log.debug("No 'note' qualifier found. Assigned feature as IRa.")
						IRa = repeat_feature
				else:
					self.log.info("Inverted repeat feature detected at position %s - %s. Region is too small (smaller than %s bp) to be IRa or IRb." % \
					  (str(repeat_feature.location.start), str(repeat_feature.location.end), str(min_IR_len)))
		if IRa is None or IRb is None:
			self.log.debug("%s out of 2 IR positions found so far. Checking repeat_features without 'rpt_type' qualifier." % \
			  (str([IRa is None, IRb is None].count(False))))
			i = 0
			for repeat_feature in [feature for feature in all_repeat_features if not "rpt_type" in feature.qualifiers]:
				i += 1
				self.log.debug("Checking repeat_feature %s out of %s (position %s - %s)..." % \
				  (str(i), str(len(all_repeat_features)), str(repeat_feature.location.start), str(repeat_feature.location.end)))
				if "note" in repeat_feature.qualifiers:
					self.log.debug("Checking note qualifier for IR identifiers...")
					if any(identifier in repeat_feature.qualifiers["note"][0].lower() for identifier in ira_identifiers):
						self.log.debug("Found identifier for IRa.")
						IRa = repeat_feature
					elif any(identifier in repeat_feature.qualifiers["note"][0].lower() for identifier in irb_identifiers):
						self.log.debug("Found identifier for IRb.")
						IRb = repeat_feature
					elif ("inverted" in repeat_feature.qualifiers["note"][0].lower() and "repeat" in repeat_feature.qualifiers["note"][0].lower()) or "IR" in repeat_feature.qualifiers["note"][0]:
						self.log.debug("Found general identifier for IRs.")
						# IRb gets assigned first, since it is located before IRa in the sequence, so if there
						# is no further information given, the first IR found is assumed to be IRb.
						if IRb is None:
							self.log.debug("Assign feature as IRb.")
							IRb = repeat_feature
						# Note: Elif-statement in this context assures that IRa is assigned only if IRb is not None.
						elif IRa is None:
							self.log.debug("Assigned feature as IRa.")
							IRa = repeat_feature
					else:
						self.log.info("Found a repeat region (%s - %s) without further identifying information. Ignoring this feature." % \
						  (str(repeat_feature.location.start), str(repeat_feature.location.end)))
		
		return IRa, IRb

	def identify_inverted_repeats(self, rec, min_IR_len=1000):
		'''
		Tries to identify Inverted Repeats in a SeqRecord.
		Params:
		 - rec: the SeqRecord
		 - min_IR_len: minimum length identified IRs must have.
		Returns:
		 - IRa: SeqFeature object corresponding to the SeqRecord's Inverted Repeat A
		 - IRb: SeqFeature object corresponding to the SeqRecord's Inverted Repeat B
		'''
		IRa = None
		IRb = None
		self.log.debug("Trying to determine IRs...")

		# STEP 1. Parse out all potentially relevant features
		all_repeat_features = [feature for feature in rec.features if feature.type=='repeat_region']
		all_misc_features = [feature for feature in rec.features if feature.type=='misc_feature']
		# Note: The following line prevents that pseudogenes (or related pseudo-features)
		#       are used to infer the IR length.
		all_mf_no_pseudo = [feature for feature in all_misc_features if 'pseudo' not in feature.qualifiers]
		
		if len(all_repeat_features) == 0 and len(all_misc_features) == 0:
			raise Exception("Record does not contain any features which the IR are typically marked with (i.e., feature `repeat_region`, `misc_feature`).")		

		# STEP 2: Loop through repeat_regions and attempt to identify IRs
		IRa, IRb = self.identify_irs_in_repeat_features(all_repeat_features, IRa, IRb, min_IR_len)
		
		# If no valid IRs found, check if the misc_features contain "note" qualifiers necessary for identification
		if IRa is None and IRb is None:
			all_qualifiers = [misc_feature.qualifiers for misc_feature in all_misc_features]
			# The following line generates a nested list of all keys of all qualifiers found in all misc features
			keylist = [list(q) for q in all_qualifiers]
			if "note" not in [key for keys in keylist for key in keys]: # Flatten the key list
				raise Exception("Record does not contain any qualifiers for feature `misc_feature` which the IRs are typically named with (i.e., qualifier `note`).")
		
		# STEP 3. Loop through misc_features and attempt to identify IRs
		if IRa is None or IRb is None:
			self.log.debug("%s out of 2 IR positions found so far. Checking all misc_features for identifying information in their NOTE QUALIFIERS..." % \
			  (str([IRa is None, IRb is None].count(False))))
			IRa, IRb = self.identify_irs_in_misc_features(all_mf_no_pseudo, IRa, IRb)
		
		# Sanity check for IRs selected by the script so far
		if IRa is not None and len(IRa.extract(rec).seq) < min_IR_len:
			self.log.warning("Selected IRa is too short to be a genuine IR and has been discarded.")
			IRa = None
		if IRb is not None and len(IRb.extract(rec).seq) < min_IR_len:
			self.log.warning("Selected IRb is too short to be a genuine IR and has been discarded.")
			IRb = None
			
		# STEP 4. Loop through misc_features and attempt to identify junctions from which to infer the IRs
		if IRa is None or IRb is None:
			self.log.debug("%s out of 2 IR positions found so far. Checking all misc_features for JUNCTION INFORMATION..." % \
			  (str([IRa is None, IRb is None].count(False))))				
			IRa, IRb = self.infer_irs_from_junctions(len(rec), all_misc_features)
			
		# Sanity check for IRs selected by the script so far
		if IRa is not None and len(IRa.extract(rec).seq) < min_IR_len:
			self.log.warning("Selected IRa is too short to be a genuine IR and has been discarded.")
			IRa = None
		if IRb is not None and len(IRb.extract(rec).seq) < min_IR_len:
			self.log.warning("Selected IRb is too short to be a genuine IR and has been discarded.")
			IRb = None

		# STEP 5. Inferring the position of the IR implicitly by extracting the positions of the large (LSC) and
		# small single copy (SSC) regions and calculating the IRs as the complement set thereof.
		if IRa is None or IRb is None:
			self.log.debug("%s out of 2 IR positions found so far. Trying to infer the missing IRs by given single-copy region positions..." % \
			  (str([IRa is None, IRb is None].count(False))))
			if len(all_mf_no_pseudo) == 0:
				if IRa is None and IRb is None:
					raise Exception("Record does not contain any features which the single-copy regions are typically marked with (i.e., feature `misc_feature`).")
			IRa, IRb = self.infer_irs_from_single_copy_regions(len(rec), all_mf_no_pseudo, IRa, IRb)
			
		# Sanity check for IRs selected by the script so far
		if IRa is not None and len(IRa.extract(rec).seq) < min_IR_len:
			self.log.warning("Selected IRa is too short to be a genuine IR and has been discarded.")
			IRa = None
		if IRb is not None and len(IRb.extract(rec).seq) < min_IR_len:
			self.log.warning("Selected IRb is too short to be a genuine IR and has been discarded.")
			IRb = None
			
		if IRa is None and IRb is None:
			raise Exception("Record does not contain the information necessary to infer the position of either the IR or the single-copy regions.")
		
		return IRa, IRb
	

	########
	# MISC #
	########

	def adjust_feature_location(self, feature):
		'''
		Checks that start and end position of a feature are not identical; if they are,
		make start position one bp less than end position; returns the adjusted feature
		(Some junctions in Genbank format are given as "start^end", leading to start and
		end positions being the same.)
		Params:
		 - feature: the SeqFeature
		'''
		if feature:
			if feature.location.start == feature.location.end:
				feature.location = FeatureLocation(feature.location.start-1, feature.location.end, strand = feature.strand)
				self.log.debug("Adjusted FeatureLocation to %s" % str(feature.location))
		return feature
	
	def collect_info_from_features(self, ira_feature, irb_feature):
		fields = {}
		if ira_feature:
			fields["IRa_REPORTED"] = "yes"
			fields["IRa_REPORTED_START"] = ira_feature.location.start + 1
			fields["IRa_REPORTED_END"] = ira_feature.location.end
			fields["IRa_REPORTED_LENGTH"] = str(len(ira_feature))
		else:
			fields["IRa_REPORTED"] = "no"
			fields["IRa_REPORTED_START"] = "n.a."
			fields["IRa_REPORTED_END"] = "n.a."
			fields["IRa_REPORTED_LENGTH"] = "n.a."
		if irb_feature:
			fields["IRb_REPORTED"] = "yes"
			fields["IRb_REPORTED_START"] = irb_feature.location.start + 1
			fields["IRb_REPORTED_END"] = irb_feature.location.end
			fields["IRb_REPORTED_LENGTH"] = str(len(irb_feature))
		else:
			fields["IRb_REPORTED"] = "no"
			fields["IRb_REPORTED_START"] = "n.a."
			fields["IRb_REPORTED_END"] = "n.a."
			fields["IRb_REPORTED_LENGTH"] = "n.a."
		return fields
		
class Plastome_Availability:

	def __init__(self, fp_entry_table, fp_ir_table = None, fp_blacklist = None, fp_duplicates = None):	
		self.entry_table = None
		self.duplicates = {}
		self.ir_table = None
		self.blacklist = []
		
		self.read_entry_table(os.path.abspath(fp_entry_table))		
		
		if fp_ir_table:
			self.read_ir_table(os.path.abspath(fp_ir_table))
		if fp_blacklist:
			self.read_blacklist(os.path.abspath(fp_blacklist))
		if fp_duplicates:
			self.read_duplicates(os.path.abspath(fp_duplicates))
	
	###############
	# I/O methods #
	###############
		
	def read_entry_table(self, fp_entry_table):
		'''
		Read a tab-separated file of GenBank entry information.
		If the file doesn't exist yet, create it and write column headers
		Params:
		 - fp_entry_table: file path to input file
		'''
		if os.path.isfile(fp_entry_table):
			self.entry_table = pd.read_csv(fp_entry_table, sep = '\t', index_col = 0, encoding = 'utf-8')
		else:
			columns = ["UID", "ACCESSION", "VERSION", "ORGANISM", "SEQ_LEN", "CREATE_DATE", "AUTHORS", "TITLE", "REFERENCE", "NOTE", "TAXONOMY"]
			self.entry_table = pd.DataFrame(columns = columns)
			self.entry_table = self.entry_table.set_index("UID", drop = True)
			self.write_entry_table(fp_entry_table)
	
	def write_entry_table(self, fp_entry_table, append = False):
		'''
		Write a list of GenBank entry information to tab-separated file.
		Params:
		 - fp_entry_table: file path to output file
		'''
		if append:
			self.entry_table.to_csv(fp_entry_table, sep = '\t', encoding = 'utf-8', header = False, mode = "a")
		else:			
			self.entry_table.to_csv(fp_entry_table, sep = '\t', encoding = 'utf-8', header = True)
	
	def append_entry_to_table(self, entry, uid, fp_entry_table):
		'''
		Write information on one GenBank entry to tab-separated file
		Params:
		 - entry: dict. Keys are column names
		 - uid: Unique identifier for this GenBank entry
		 - fp_entry_table: file path to output file
		'''
		if os.path.isfile(fp_entry_table):
			for key, value in entry.items():
				entry[key] = [value]
			entry["UID"] = [uid]
			temp_df = pd.DataFrame(entry)
			temp_df = temp_df.set_index("ACCESSION", drop = True)
			temp_df.to_csv(fp_ir_table, sep = '\t', header = False, encoding = 'utf-8', mode = "a")
		else:
			raise Exception("Error trying to append GenBank entry to file '%s': File does not exist!" % (fp_entry_table))
		
	def read_ir_table(self, fp_ir_table):
		'''
		Read a tab-separated file of information on inverted repeats per GenBank accession
		If the file doesn't exist yet, create it and write column headers
		Params:
		 - fp_ir_table: file path to input file		
		'''
		if os.path.isfile(fp_ir_table):
			self.ir_table = pd.read_csv(fp_ir_table, sep = '\t', index_col = 0, encoding = 'utf-8')
		else:
			columns = ["ACCESSION", "IRa_REPORTED", "IRa_REPORTED_START", "IRa_REPORTED_END", "IRa_REPORTED_LENGTH", "IRb_REPORTED", "IRb_REPORTED_START", "IRb_REPORTED_END", "IRb_REPORTED_LENGTH"]
			self.ir_table = pd.DataFrame(columns = columns)
			self.ir_table = self.ir_table.set_index("ACCESSION", drop = True)
			self.write_ir_table(fp_ir_table)
			
	def write_ir_table(self, fp_ir_table, append = False):
		'''
		Write a list of per-accession inverted repeat information to tab-separated file
		Params:
		 - fp_ir_table: file path to output file
		'''
		if append:
			self.ir_table.to_csv(fp_ir_table, sep = '\t', encoding = 'utf-8', header = False, mode = "a")
		else:
			self.ir_table.to_csv(fp_ir_table, sep = '\t', encoding = 'utf-8', header = True)
			
	def append_ir_info_to_table(self, ir_info, accession, fp_ir_table):
		'''
		Write information on one accession's inverted repeats to tab-separated file
		Params:
		 - ir_info: dict. Keys are column names
		 - accession: accession number of this record
		 - fp_ir_table: file path to output file
		'''
		if os.path.isfile(fp_ir_table):
			for key, value in ir_info.items():
				ir_info[key] = [value]
			ir_info["ACCESSION"] = [accession]
			temp_df = pd.DataFrame(ir_info)
			temp_df = temp_df.set_index("ACCESSION", drop = True)
			temp_df.to_csv(fp_ir_table, sep = '\t', header = False, encoding = 'utf-8', mode = "a")
		else:
			raise Exception("Error trying to append IR info to file '%s': File does not exist!" % (fp_ir_table))
	
	def read_blacklist(self, fp_blacklist):
		'''
		Read a file of blacklisted genera.
		Params:
		 - fp_blacklist: file path to input file
		'''
		with open(fp_blacklist, "r") as fh_blacklist:
			for line in [l.rstrip() for l in fh_blacklist.readlines()]:
				if not line.startswith("#"):
					self.blacklist.append(line)
				
	def read_duplicates(self, fp_duplicates):
		'''
		Read a tab-separated file of RefSeq accession numbers and corresponding duplicate accession numbers.
		Params:
		 - fp_duplicates: file path to input file
		'''
		with open(fp_duplicates, "r") as fh_duplicates:
			for dup_tup in [line.rstrip().split('\t') for line in fh_duplicates.readlines()]:
				self.duplicates[dup_tup[0]] = dup_tup[1]
		
	def write_duplicates(self, fp_duplicates):
		'''
		Write a list of RefSeq accession numbers and corresponding duplicate accession numbers to tab-separated file.
		Params:
		 - fp_duplicates: file path to output file
		'''
		with open(fp_duplicates, "w") as fh_duplicates:
			for d_key in self.duplicates.keys():
				fh_duplicates.write("%s\t%s\n" % (str(d_key), str(self.duplicates[d_key])))
				
	def append_duplicates(self, fp_duplicates):
		'''
		Append a list of RefSeq accession numbers and corresponding duplicate accession numbers to tab-separated file.
		Params:
		 - fp_duplicates: file path to output file
		'''
		with open(fp_duplicates, "a") as fh_duplicates:
			for d_key in self.duplicates.keys():
				fh_duplicates.write("%s\t%s\n" % (str(d_key), str(self.duplicates[d_key])))
	
	#####################
	# List edit methods #
	#####################
					
	def remove_blacklisted_entries(self):
		'''
		Remove entries from entry table that match blacklisted genera.
		'''		
		for genus in self.blacklist:
			# TM: The next line took a while to figure out, so for the sake of my own and future contributers' sanities, here's a breakdown of what it does:
			# self.entry_table["TAXONOMY"].str provides the whole taxonomy column for elementwise(i.e. rowwise) string operations. Since our TAXONOMY information is semicolon-separated, each row is split.
			# This results in a Series of string lists. The last element (the genus) of each string list is compared to the current genus from the blacklist (entry[-1].rstrip('.') == genus).
			# This in turn results in a list of bools, making self.entry_table.loc return all rows where the list of bools has True (i.e. all entries that match a blacklisted entry)
			# Finally, we want only the index of those rows, to tell the dataframe which ones should get dropped.
			self.entry_table.drop(self.entry_table.loc[[(entry[-1].rstrip('.') == genus) for entry in self.entry_table["TAXONOMY"].str.split(';')]].index, inplace = True)
		if len(self.blacklist) == 0:
			self.log.info("Blacklist is empty. No entries removed.")
	
	def remove_duplicates(self):
		'''
		Remove entries from entry table that match duplicate accession numbers
		'''
		for d_key in self.duplicates.keys():
			self.entry_table.drop(self.entry_table.loc[self.entry_table["ACCESSION"] == self.duplicates[d_key]].index, inplace = True)
			
		
		
