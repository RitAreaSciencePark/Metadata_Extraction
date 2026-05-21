# SPDX-FileCopyrightText: 2026  Lesly TSOPTIO FOUGANG, Valerio PIOMPONI, Ornella AFFINITO,
# Laboratory of Data Engineering, Research and Technology Institute (RIT),
# Area Science Park, Trieste, Italy.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import datetime
import json
from rocrate.rocrate import ROCrate
from rocrate.model.contextentity import ContextEntity
from rocrate.model.entity import Entity
from rocrate.model.dataset import Dataset

import Extractor_BeadStudio
import Extractor_Thermal_Report
import Extractor_FMGeneration
import Extractor_IlluminaSampleSheet
import Extractor_FMAutoTilt
import Extractor_Nanopore
import Extractor_SampleReport
import Extractor_SampleSheet_xlsx
import Extractor_NanoDrop_QC
import Extractor_FastQC


def get_readable_file_size(size_in_bytes):
    """Convert bytes to a human-readable string (e.g., '1.20 MB')."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} TB"


def generate_folder_rocrate(input_folder):

    # ------------------------------------------------------------------ #
    #  Specific descriptions keyed on Nanopore file sub-type strings      #
    # ------------------------------------------------------------------ #
    FILE_DESCRIPTIONS = {
        "pod5_file": "Represent raw signal data captured by the Nanopore device, "
                     "used for quality control and re-basecalling.",
        "fastq_file": "A text-based sequence storage format, containing both the "
                      "sequence of DNA/RNA and its quality scores.",
        "bam_file": "Binary format for storing aligned sequencing reads, containing "
                    "both sequence and alignment information.",
        "bam_index_file": "Index file for BAM files, enabling rapid access to "
                          "specific regions within the BAM file for downstream analysis.",
        "sample_sheet": "Tabular data file containing sample identifiers and "
                        "experimental metadata for downstream analysis.",
        "sequencing_summary": "Quantitative summary of the sequencing run, "
                              "including read lengths and quality scores.",
        "json_report": "Machine-readable report containing instrument metadata "
                       "and execution parameters.",
        "report_in_markdown": "Human-readable summary of the sequencing run "
                              "and primary analysis results.",
        "final_summary": "Text-based summary of the final basecalling and run metrics.",
    }

    input_folder_name = os.path.basename(os.path.normpath(input_folder))

    VALID_EXTENSIONS = (
        '.csv', '.txt', '.json', '.md', '.pod5', '.fastq.gz',
        '.bam', '.bam.bai', '.xlsx', '.pdf', '.jpeg', '.png',
        '.zip', '.log', '.html', '.tiff', '.xml', '.xad',
    )

    # ------------------------------------------------------------------ #
    #  MIME map now used directly as encodingFormat strings        #
    #          for standard types; entity refs kept only for custom types  #
    # ------------------------------------------------------------------ #
    MIME_MAP = {
        '.csv':      'text/csv',
        '.txt':      'text/plain',
        '.md':       'text/markdown',
        '.json':     'application/json',
        '.pdf':      'application/pdf',
        '.jpeg':     'image/jpeg',
        '.xlsx':     'application/vnd.openxmlformats-officedocument'
                     '.spreadsheetml.sheet',
        '.zip':      'application/zip',
        '.html':     'text/html',
        '.tiff':     'image/tiff',
        '.xml':      'application/xml',
        '.log':      'text/plain',
        # Non-standard MIME types — these still reference format entities
        '.pod5':     'application/vnd.nanopore.pod5',
        '.fastq.gz': 'application/fastq',
        '.bam':      'application/x-bam',
        '.bam.bai':  'application/x-bam-index',
        '.xad':      'application/xad',
    }

    # Extensions whose MIME types are non-standard → keep entity reference
    NON_STANDARD_MIMES = {
        'application/vnd.nanopore.pod5',
        'application/fastq',
        'application/x-bam',
        'application/x-bam-index',
        'application/xad',
    }

    # ------------------------------------------------------------------ #
    #  Pre-scan: detect instrument types and count extensions             #
    # ------------------------------------------------------------------ #
    print(f" Pre-scanning folder for file types in: {input_folder}")

    detected_labels = set()
    extension_counts = {}
    global_sequencer_type = None

    for root, dirs, files in os.walk(input_folder):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if filename.lower().endswith('.fastq.gz'):
                ext = '.fastq.gz'
            if filename.lower().endswith('.bam.bai'):
                ext = '.bam.bai'
            if ext not in VALID_EXTENSIONS:
                continue

            extension_counts[ext] = extension_counts.get(ext, 0) + 1
            full_path = os.path.join(root, filename)

            if (Extractor_IlluminaSampleSheet.is_illumina_samplesheet(full_path) or
                    Extractor_SampleReport.is_samples_report(full_path)):
                detected_labels.add(
                    "<b>Sequencing phase</b>: runs performed using Illumina NovaSeq6000")
                global_sequencer_type = "NOVASEQ"
            elif Extractor_Nanopore.is_nanopore_file(full_path):
                detected_labels.add(
                    "<b>Sequencing phase</b>: runs performed using Oxford Nanopore PromethION")
                global_sequencer_type = "NANOPORE"
            elif Extractor_BeadStudio.is_beadstudio_file(full_path):
                detected_labels.add(
                    "<b>Sequencing phase</b>: runs performed using Illumina iScan")
                global_sequencer_type = "ISCAN"
            elif Extractor_NanoDrop_QC.is_nanodrop_export(full_path):
                detected_labels.add(
                    "<b>Pre-sequencing Quality control phase</b>: "
                    "NanoDrop UV absorbance spectrum for each sample")
            elif Extractor_SampleSheet_xlsx.is_lab_samplesheet(full_path):
                detected_labels.add(
                    "<b>Sample quality assessment phase</b> (Sample and plate metadata): "
                    "description of samples and plate layout used for sequencing.")
            elif Extractor_FastQC.is_fastqc_zip(full_path):
                detected_labels.add(
                    "<b>Post-sequencing Quality check phase</b>: FastQC quality control "
                    "report archive generated by FastQC software Babraham Bioinformatics")

    total_files = sum(extension_counts.values())

    file_summary_parts = [
        f"{count} <b>{ext}</b> files" for ext, count in extension_counts.items()
    ]
    file_summary_html = (
        "<ul>" + "".join(f"<li>{p}</li>" for p in file_summary_parts) + "</ul>"
        if file_summary_parts else "<i>No valid data files detected.</i>"
    )
    types_html = (
        "<ul>" + "".join(f"<li>{l}</li>" for l in detected_labels) + "</ul>"
        if detected_labels else "<i>Unknown Instrument Type</i>"
    )

    # ------------------------------------------------------------------ #
    #  ROCrate() conformsTo to 1.2      #
    # ------------------------------------------------------------------ #
    crate = ROCrate()

    # Force conformsTo to RO-Crate 1.2
    metadata_descriptor = crate.metadata
    metadata_descriptor["conformsTo"] = {"@id": "https://w3id.org/ro/crate/1.2"}

    # ------------------------------------------------------------------ #
    #  Root Dataset                                                        #
    # ------------------------------------------------------------------ #
    crate.root_dataset["name"] = (
        f"LAGE Experimental Dataset for the Repository: {input_folder_name}"
    )
    crate.root_dataset["description"] = (
        f"<p>This dataset contains <b>{total_files}</b> files generated through:</p>"
        f"{types_html}"
        "<p>It also includes <b>RO-Crate metadata</b> file (ro-crate-metadata.json) "
        "that describes the context of data generation, such as the laboratory "
        "environment, the research institute, and the instruments used.</p>"
    )
    crate.root_dataset["license"] = "https://opensource.org/licenses/MIT"
    crate.root_dataset["keywords"] = [
        "Area Science Park", "LAGE", "LADE", "RIT",
        "Genomics", "Metadata", "Sequencing",
    ]
    crate.root_dataset["datePublished"] = datetime.datetime.now().date().isoformat()

    # ------------------------------------------------------------------ #
    #  Organisations                                                       #
    # ------------------------------------------------------------------ #
    area_science_park = crate.add(ContextEntity(crate, "#area-science-park", properties={
        "@type": "Organization",
        "name": "Area Science Park",
        "url": "https://www.areasciencepark.it/en/",
    }))
    rit = crate.add(ContextEntity(crate, "#rit", properties={
        "@type": "Organization",
        "name": "Research and Technology Institute (RIT)",
        "parentOrganization": {"@id": area_science_park.id},
    }))
    lade = crate.add(ContextEntity(crate, "#lade", properties={
        "@type": "Organization",
        "name": "Laboratory of Data Engineering (LADE)",
        "url": "https://www.areasciencepark.it/infrastrutture-di-ricerca/data-engineering-lade/",
        "parentOrganization": {"@id": rit.id},
    }))
    lage = crate.add(ContextEntity(crate, "#lage", properties={
        "@type": "Organization",
        "name": "Laboratory of Genomics and Epigenomics (LAGE)",
        "url": "https://www.areasciencepark.it/en/research-infrastructures/"
               "life-sciences/lage-genomics-and-epigenomics-laboratory/",
        "parentOrganization": {"@id": rit.id},
    }))

    # ------------------------------------------------------------------ #
    #  Software entities                                                   #
    # ------------------------------------------------------------------ #
    ro_crate_script = crate.add(ContextEntity(crate, "#Crate_Generator", properties={
        "@type": "SoftwareApplication",   # FIX 6: was "softwareApplication"
        "name": "LAGE Folder Descriptor Generator",
        "description": "Script to generate RO-Crate descriptors for lab raw data folders.",
        "creator": {"@id": lade.id},
        "license": "https://opensource.org/licenses/MIT",
        "url": "https://github.com/RitAreaSciencePark/LAGE_Metadata_Extraction"
               "/blob/main/Src/Crate_Generator.py",
    }))
    history_tool = crate.add(ContextEntity(crate, "#History_Extractor", properties={
        "@type": "SoftwareApplication",   # FIX 6
        "name": "LAGE Sample History Extractor",
        "description": "Logic used to reconstruct sample-centric provenance "
                       "from fragmented metadata.",
        "creator": {"@id": lade.id},
    }))

    # ------------------------------------------------------------------ #
    #  FastQC entity type corrected                                #
    # ------------------------------------------------------------------ #
    fastqc_software = crate.add(ContextEntity(crate, "#fastqc-software", properties={
        "@type": "SoftwareApplication",   # FIX 6: was "softwareApplication"
        "name": "FastQC from Babraham Bioinformatics",
        "version": "0.12.1",
        "url": "https://www.bioinformatics.babraham.ac.uk/projects/fastqc/",
    }))

    # ------------------------------------------------------------------ #
    #  Instruments & Activities                                           #
    # ------------------------------------------------------------------ #
    instrument_nano = crate.add(ContextEntity(crate, "#promethion-device", properties={
        "@type": "Device",
        "name": "Oxford Nanopore PromethION",
        "manufacturer": "Oxford Nanopore Technologies",
        "model": "PromethION 24/48",
        "url": "https://nanoporetech.com/products/promethion",
    }))
    #  result[] will be populated after the file walk
    run_nano = crate.add(ContextEntity(crate, "#nanopore-sequencing-activity", properties={
        "@type": "CreateAction",
        "name": "Nanopore Sequencing Run",
        "instrument": {"@id": instrument_nano.id},
    }))

    instrument_iscan = crate.add(ContextEntity(crate, "#iscan-device", properties={
        "@type": "Device",
        "name": "Illumina iScan",
        "manufacturer": "Illumina",
        "model": "iScan 24/48",
        "url": "https://www.illumina.com/systems/array-scanners/iscan.html",
    }))
    run_iscan = crate.add(ContextEntity(crate, "#iscan-scanning-activity", properties={
        "@type": "CreateAction",
        "name": "Illumina iScan Scanning Run",
        "instrument": {"@id": instrument_iscan.id},
    }))

    instrument_novaseq = crate.add(ContextEntity(crate, "#novaseq-device", properties={
        "@type": "Device",
        "name": "Illumina NovaSeq 6000",
        "manufacturer": "Illumina",
        "model": "NovaSeq 6000",
        "url": "https://www.illumina.com/systems/sequencing-platforms/novaseq.html",
    }))
    run_novaseq = crate.add(ContextEntity(crate, "#novaseq-sequencing-activity", properties={
        "@type": "CreateAction",
        "name": "Illumina NovaSeq Sequencing Run",
        "instrument": {"@id": instrument_novaseq.id},
    }))

    instrument_tapestation = crate.add(ContextEntity(crate, "#tapestation-device", properties={
        "@type": "Device",
        "name": "Agilent TapeStation 4200",
        "manufacturer": "Agilent Technologies",
        "model": "TapeStation 4200",
        "url": "https://www.agilent.com/en/products/tapestation",
    }))
    run_tapestation = crate.add(ContextEntity(
        crate, "#tapestation-quality-control-activity", properties={
            "@type": "CreateAction",
            "name": "TapeStation Quality Control",
            "description": "Quality control process for samples before sequencing, "
                           "including electrophoretic analysis using the Agilent "
                           "TapeStation 4200 to assess DNA/RNA integrity and size distribution.",
            "instrument": {"@id": instrument_tapestation.id},
        }))

    qc_activity = crate.add(ContextEntity(crate, "#quality-control-activity", properties={
        "@type": "CreateAction",
        "name": "Sample Quality Control",
        "description": "Quality control process for samples before sequencing, which may "
                       "include NanoDrop UV absorbance measurements, report of technical "
                       "observations and anomalies detected (both before and after "
                       "sequencing), and other QC steps.",
    }))
    post_qc_activity = crate.add(ContextEntity(
        crate, "#post-sequencing-quality-control-activity", properties={
            "@type": "CreateAction",
            "name": "Post-Sequencing Quality Control",
            "description": "Quality control process after sequencing, which includes "
                           "FastQC analysis of raw FASTQ files.",
            "instrument": {"@id": fastqc_software.id},
        }))
    acceptance_activity = crate.add(ContextEntity(crate, "#acceptance-activity", properties={
        "@type": "CreateAction",
        "name": "Sample Acceptance Phase",
        "description": "Initial phase where the researcher or client provides the "
                       "samples and plate scheme description before sequencing.",
    }))

    # ------------------------------------------------------------------ #
    #   Format entities use "MediaType" instead of "File Format"   #
    #  These are kept only for non-standard MIME types.                   #
    #  Standard MIME types are now written as plain strings.      #
    # ------------------------------------------------------------------ #
    pod5_format = crate.add(ContextEntity(crate, "#pod5-format", properties={
        "@type": "MediaType",
        "name": "POD5",
        "description": "Nanopore raw signal data format replacing FAST5.",
        "url": "https://software-docs.nanoporetech.com/pod5/latest/",
    }))
    fastq_gz_format = crate.add(ContextEntity(crate, "#fastq-gz-format", properties={
        "@type": "MediaType",
        "name": "FASTQ GZipped",
        "description": "Gzipped FASTQ format for storing biological sequences and "
                       "quality scores, generated during the post-sequencing basecalling step.",
        "url": "https://knowledge.illumina.com/software/general/"
               "software-general-reference_material-list/000002211.html",
    }))
    bam_format = crate.add(ContextEntity(crate, "#bam-format", properties={
        "@type": "MediaType",
        "name": "BAM (Binary Alignment Map)",
        "description": "Binary representation of the Sequence Alignment/Map (SAM) format.",
        "url": "https://support.illumina.com/help/BS_App_RNASeq_Alignment_OLH_"
               "1000000006112/Content/Source/Informatics/BAM-Format.htm",
    }))
    bai_format = crate.add(ContextEntity(crate, "#bai-format", properties={
        "@type": "MediaType",
        "name": "BAI (BAM Index)",
        "description": "Index file for rapid access to BAM alignment files.",
        "url": "https://en.wikipedia.org/wiki/BAI_(file_format)",
    }))
    # XAD format — placeholder URL removed; no url property included
    xad_format = crate.add(ContextEntity(crate, "#xad-format", properties={
        "@type": "MediaType",
        "name": "XAD Archive",
        "description": "Custom archive format used for storing complex datasets "
                       "with embedded metadata.",
    }))

    # Map non-standard MIME types to their format entity @id
    FORMAT_ENTITY_MAP = {
        'application/vnd.nanopore.pod5': pod5_format.id,
        'application/fastq':            fastq_gz_format.id,
        'application/x-bam':            bam_format.id,
        'application/x-bam-index':      bai_format.id,
        'application/xad':              xad_format.id,
    }

    # ------------------------------------------------------------------ #
    #  Main folder Dataset entity                                         #
    # ------------------------------------------------------------------ #
    folder_id = f"{input_folder_name}/"
    folder_entity = crate.add(ContextEntity(crate, folder_id, properties={
        "@type": "Dataset",
        "name": input_folder_name,
        "description": (
            "<p>Main data directory containing outputs from the following phases:</p>"
            f"{types_html}"
            "<p>This dataset includes:</p>"
            f"{file_summary_html}"
        ),
        "hasPart": [],
    }))
    crate.root_dataset["hasPart"] = [{"@id": folder_id}]

    # ------------------------------------------------------------------ #
    #  State tracking                                                     #
    # ------------------------------------------------------------------ #
    folder_entities = {".": folder_entity}
    subfolder_sizes = {}
    total_folder_size = 0
    count = 0
    seen_files = {}

    # Accumulate result lists per activity
    activity_results = {
        run_novaseq.id:     [],
        run_nano.id:        [],
        run_iscan.id:       [],
        run_tapestation.id: [],
        qc_activity.id:     [],
        post_qc_activity.id:[],
        acceptance_activity.id: [],
    }

    # ------------------------------------------------------------------ #
    #  File walk                                                          #
    # ------------------------------------------------------------------ #
    for root, dirs, files in os.walk(input_folder):
        rel_root = os.path.relpath(root, input_folder)

        # Sub-directory handling
        if rel_root != "." and (len(files) > 0 or len(dirs) >= 1):
            if rel_root not in folder_entities:
                folder_name = os.path.basename(root)
                current_folder_id = f"{rel_root}/"
                new_dataset = crate.add(ContextEntity(crate, current_folder_id, properties={
                    "@type": "Dataset",
                    "name": folder_name,
                    "description": f"Directory containing <b>{folder_name}</b> data.",
                    "hasPart": [],
                }))
                folder_entities[rel_root] = new_dataset
                parent_path = os.path.dirname(rel_root)
                actual_parent_key = parent_path if parent_path != "" else "."
                if actual_parent_key in folder_entities:
                    parent_entity = folder_entities[actual_parent_key]
                    p_parts = parent_entity.get("hasPart", [])
                    if not isinstance(p_parts, list):
                        p_parts = [p_parts]
                    p_parts.append({"@id": current_folder_id})
                    parent_entity["hasPart"] = p_parts

        current_parent_entity = folder_entities.get(rel_root, folder_entity)

        for filename in files:
            if filename == "ro-crate-metadata.json":
                continue
            if not filename.lower().endswith(VALID_EXTENSIONS):
                continue

            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, input_folder)
            file_size_bytes = os.path.getsize(full_path)
            readable_size = get_readable_file_size(file_size_bytes)
            total_folder_size += file_size_bytes

            # ---------------------------------------------------------- #
            #  History file special case                                   #
            # ---------------------------------------------------------- #
            if filename.startswith("History_") and filename.endswith(".json"):
                target_sample_id = filename.replace("History_", "").replace(".json", "")
                try:
                    with open(full_path, 'r') as hf:
                        history_data = json.load(hf)
                    num_entries = len(history_data)

                    file_props = crate.add_file(full_path, dest_path=rel_path, properties={
                        "name": filename,
                        "description": (
                            f"Provenance Dataset for Sample: <b>{target_sample_id}</b>. "
                            f"This file aggregates <b>{num_entries}</b> experimental records."
                        ),
                        "creator": {"@id": lage.id},
                        "datePublished": datetime.datetime.now().date().isoformat(),
                        #  standard MIME type as plain string
                        "encodingFormat": "application/json",
                        "humanReadableSize": readable_size,
                        "wasGeneratedBy": {"@id": history_tool.id},
                    })

                    root_parts = crate.root_dataset.get("hasPart", [])
                    if isinstance(root_parts, list):
                        root_parts = [p for p in root_parts if p.get("@id") != rel_path]
                        crate.root_dataset["hasPart"] = root_parts

                    # FIX 3: source @id prefixed with # → not treated as physical files
                    source_ids = []
                    for entry in history_data:
                        src_name = entry.get('source_file') or entry.get('file_name')
                        if not src_name:
                            continue
                        safe_name = src_name.replace('/', '-').replace(' ', '_')
                        src_id = f"#source-{safe_name}"
                        if any(s["@id"] == src_id for s in source_ids):
                            continue
                        if src_id not in seen_files:
                            crate.add(ContextEntity(crate, src_id, properties={
                                "@type": "File",
                                "name": src_name,
                                "description": f"Metadata source file for sample "
                                               f"{target_sample_id}.",
                                "creator": {"@id": lage.id},
                                "encodingFormat": "application/json",
                            }))
                            seen_files[src_id] = src_id
                        source_ids.append({"@id": src_id})

                    file_props["derivedFrom"] = source_ids

                    f_parts = current_parent_entity.get("hasPart", [])
                    if not isinstance(f_parts, list):
                        f_parts = [f_parts]
                    if {"@id": rel_path} not in f_parts:
                        f_parts.append({"@id": rel_path})
                    current_parent_entity["hasPart"] = f_parts
                    count += 1
                    continue

                except Exception as e:
                    print(f"Error processing history file {filename}: {e}")

            subfolder_sizes[rel_root] = subfolder_sizes.get(rel_root, 0) + file_size_bytes

            # Extension detection
            if filename.lower().endswith('.fastq.gz'):
                ext = '.fastq.gz'
            elif filename.lower().endswith('.bam.bai'):
                ext = '.bam.bai'
            else:
                ext = os.path.splitext(filename)[1].lower()

            assigned_run = None
            custom_description = None
            encoding = MIME_MAP.get(ext, 'application/octet-stream')

            # FIX 4: use entity reference only for non-standard MIME types
            if encoding in NON_STANDARD_MIMES:
                encoding_value = {"@id": FORMAT_ENTITY_MAP[encoding]}
            else:
                encoding_value = encoding

            # ---------------------------------------------------------- #
            #  File type detection and activity assignment                 #
            # ---------------------------------------------------------- #
            if ext == ".fastq.gz":
                if global_sequencer_type == "NOVASEQ":
                    assigned_run = run_novaseq
                    custom_description = ("<i>Gzipped FASTQ files generated by "
                                          "the Illumina NovaSeq6000 platform.</i>")
                elif global_sequencer_type == "NANOPORE":
                    assigned_run = run_nano
                    custom_description = ("<i>Gzipped FASTQ files generated by "
                                          "Oxford Nanopore PromethION basecalling.</i>")
                else:
                    custom_description = "<i>Gzipped FASTQ sequence data.</i>"

            elif Extractor_Nanopore.is_nanopore_file(full_path):
                assigned_run = run_nano
                nanopore_subtype = Extractor_Nanopore.is_nanopore_file(full_path)
                custom_description = FILE_DESCRIPTIONS.get(nanopore_subtype)

            elif Extractor_BeadStudio.is_beadstudio_file(full_path):
                assigned_run = run_iscan
                custom_description = "<i>Illumina iScan microarray sample sheet.</i>"

            elif (Extractor_IlluminaSampleSheet.is_illumina_samplesheet(full_path) or
                  Extractor_FMAutoTilt.is_fm_autotilt_report(full_path) or
                  Extractor_FMGeneration.is_fm_generation_report(full_path) or
                  Extractor_Thermal_Report.is_thermal_report(full_path) or
                  Extractor_SampleReport.is_samples_report(full_path)):
                assigned_run = run_novaseq
                custom_description = ("<i>Instrument report or sample manifest "
                                      "associated with the Illumina NovaSeq6000 run.</i>")

            elif (Extractor_NanoDrop_QC.is_nanodrop_export(full_path)):
                assigned_run = qc_activity
                custom_description = ("<i>Quantitative sample quality control data "
                                      "exported from NanoDrop.</i>")

            elif Extractor_SampleSheet_xlsx.is_lab_samplesheet(full_path):
                assigned_run = acceptance_activity
                custom_description = ("<i>Excel file containing sample and plate scheme "
                                      "description provided by the researcher during "
                                      "the acceptance phase.</i>")

            elif Extractor_FastQC.is_fastqc_zip(full_path):
                assigned_run = post_qc_activity
                custom_description = ("<i>FastQC quality control report archive "
                                      "generated from raw FASTQ sequencing data.</i>")

            elif ext == '.pdf':
                assigned_run = qc_activity
                custom_description = ("<i>Technical report or spectral curves obtained "
                                      "during the quality control phase.</i>")

            elif ext == '.jpeg':
                assigned_run = qc_activity
                custom_description = ("<i>Visual representation related to sample "
                                      "quality control or lab observation.</i>")

            elif ext == '.xad':
                assigned_run = run_tapestation
                custom_description = ("<i>Raw analytical data including electrophoretic "
                                      "signals, run parameters, ScreenTape type, and "
                                      "sample-associated information.</i>")

            if ext in ('.png', '.tiff'):
                if "NanoDrop" in filename:
                    assigned_run = qc_activity
                    custom_description = "<i>NanoDrop absorbance curve image.</i>"
                elif "Gel" in filename:
                    assigned_run = qc_activity
                    custom_description = "<i>Electrophoresis gel image for DNA integrity check.</i>"
                else:
                    assigned_run = qc_activity
                    custom_description = "<i>Experimental image documentation.</i>"

            if not custom_description:
                if ext == '.csv':
                    custom_description = ("<i>Tabular data file containing quantitative "
                                          "results and analysis outputs.</i>")
                elif ext in ('.txt', '.md'):
                    custom_description = ("<i>Text-based file containing metadata and "
                                          "analysis outputs for data sharing.</i>")
                else:
                    custom_description = f"<i>Validated {encoding} data file.</i>"

            # ---------------------------------------------------------- #
            #  Create file entity (deduplication via seen_files)          #
            # ---------------------------------------------------------- #
            if filename in seen_files:
                file_id = seen_files[filename]
            else:
                file_id = rel_path
                file_props = Entity(crate, identifier=file_id, properties={
                    "name": filename,
                    "@type": "File",
                    "description": custom_description,
                    "creator": {"@id": lage.id},
                    "encodingFormat": encoding_value,  # FIX 4
                    "humanReadableSize": readable_size,
                    "wasGeneratedBy": {"@id": ro_crate_script.id},
                })

                if assigned_run:
                    # Keep actionProcess on file for backward compatibility
                    file_props["actionProcess"] = {"@id": assigned_run.id}
                    #  accumulate for result[] on the activity
                    if assigned_run.id in activity_results:
                        activity_results[assigned_run.id].append({"@id": rel_path})
                    print(f" File Identified & Assigned: {rel_path} -> {assigned_run.id}")
                else:
                    print(f" ⚠️ File not assigned: {rel_path}")

                crate.add(file_props)
                seen_files[filename] = file_id

            f_parts = current_parent_entity.get("hasPart", [])
            if not isinstance(f_parts, list):
                f_parts = [f_parts]
            if {"@id": rel_path} not in f_parts:
                f_parts.append({"@id": rel_path})
            current_parent_entity["hasPart"] = f_parts
            count += 1

    # ------------------------------------------------------------------ #
    #  Populate result[] on each CreateAction entity              #
    # ------------------------------------------------------------------ #
    activity_map = {
        run_novaseq.id:      run_novaseq,
        run_nano.id:         run_nano,
        run_iscan.id:        run_iscan,
        run_tapestation.id:  run_tapestation,
        qc_activity.id:      qc_activity,
        post_qc_activity.id: post_qc_activity,
        acceptance_activity.id: acceptance_activity,
    }
    for act_id, results in activity_results.items():
        if results:
            activity_map[act_id]["result"] = results

    # ------------------------------------------------------------------ #
    #  Finalise sizes and write                                           #
    # ------------------------------------------------------------------ #
    crate.root_dataset["humanReadableSize"] = get_readable_file_size(total_folder_size)
    for path, size in subfolder_sizes.items():
        entity = folder_entities.get(path)
        if entity:
            entity["humanReadableSize"] = get_readable_file_size(size)

    crate.write(input_folder)
    print(f"\n ✅ Processed {count} files successfully.")
    print(f"Generated Crate ('ro-crate-metadata.json') in: {input_folder}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate RO-Crate with RO-Crate 1.2 compliance.")
    parser.add_argument("folder_path", help="The root folder to scan.")
    args = parser.parse_args()
    if os.path.isdir(args.folder_path):
        generate_folder_rocrate(args.folder_path)
    else:
        print(f"❌ Error: {args.folder_path} is not a valid directory.")
