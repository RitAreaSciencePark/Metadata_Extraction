# SPDX-FileCopyrightText: 2026  Lesly TSOPTIO FOUGANG, Valerio PIOMPONI, Ornella AFFINITO, Laboratory of Data Engineering, Research and Technology Institute (RIT), Area Science Park, Trieste, Italy.
#
# SPDX-License-Identifier: MIT

import pandas as pd
import io
import os
import json
import argparse  
import re

# File Validation Function
    # "file_Input_path" --> Full path to the input file    
def is_beadstudio_file(file_Input_path):
    """
    Checks if the file is a valid BeadStudio file by looking for 
    the keyword BeadStudio in the [Header] section.
    """
    try:
        # We only need to check the first ~20 lines to find the header
        with open(file_Input_path, 'r') as f:
            head = [next(f).lower() for _ in range(20)]
        
        content = "".join(head)
        
        # Check for 'beadstudio' anywhere in the top of the file
        if 'beadstudio' in content:
            return True
        else:
            return False
            
    except Exception as e:
        #print(f"Error reading file for validation: {e}")
        return False
    
def get_csv_section(file_Input_path, section_name):
    """
    Extracts a specific section from a semi-structured CSV.
    Returns a pandas DataFrame.
    """
    with open(file_Input_path, 'r') as f:
        lines = f.readlines()
    
    # 1. Locate the starting line of the section
    start_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(section_name):
            start_idx = i
            break
            
    if start_idx == -1:
        raise ValueError(f"Section {section_name} not found in file.")

    # 2. Find where the section ends (either the next '[' marker or end of file)
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith('['):
            end_idx = i
            break
            
    # 3. Join 0`    the relevant lines and read into pandas
    section_content = "".join(lines[start_idx + 1 : end_idx])
    return pd.read_csv(io.StringIO(section_content))


def extract_metadata(file_Input_path):
    """
    Extract header-level metadata from a BeadStudio CSV file.
    Returns a dictionary with project name, experiment name, date, and other metadata.
    """
    metadata = {}
    
    try:
        header_df = get_csv_section(file_Input_path, '[Header]')
        
        # Extract key metadata fields
        for _, row in header_df.iterrows():
            key = row.iloc[0]
            value = row.iloc[1]
            if pd.notna(key) and pd.notna(value):
                # Store metadata with lowercase keys
                metadata[key.lower().replace(' ', '_')] = value
    except Exception as e:
        print(f"Error extracting header from {file_Input_path}: {e}")
    
    return metadata

def extract_orid_from_filename(csv_file_name):
    """
    Extracts the ORID ID from a filename if present.

    Parameters:
        file_name (str): The filename to parse.

    Returns:
        dict: {'orid': str} if ORID is found, otherwise an empty dict.
    """
    # Regex pattern: look for ORID followed by digits 
    pattern = r"(ORID\d{4})"
    match = re.search(pattern, csv_file_name)
    if match:
        return  match.group(1)
    return None

def extract_manifest_info(file_Input_path):
    """
    Extract manifest information from a BeadStudio CSV file.
    Returns the manifest ID string.
    """
    try:
        with open(file_Input_path, 'r') as f:
            lines = f.readlines()
        
        # Find the Manifests section
        for i, line in enumerate(lines):
            if line.startswith('[Manifests]'):
                # The next non-empty line should contain the manifest info
                if i + 1 < len(lines):
                    manifest_line = lines[i + 1].strip()
                    if manifest_line:
                        # Split by comma and get the second field
                        parts = manifest_line.split(',')
                        if len(parts) >= 2:
                            return parts[1].strip()
                break
    except Exception as e:
        print(f"Error extracting manifest from {file_Input_path}: {e}")
    
    return 'N/A'


def count_samples(file_Input_path):
    """
    Count the number of samples in the Data section.
    Returns the count (excluding header row).
    """
    try:
        data_df = get_csv_section(file_Input_path, '[Data]')
        return len(data_df)
    except Exception as e:
        print(f"Error counting samples from {file_Input_path}: {e}")
        return 0
    


def extract_sample_data(file_Input_path):
    """
    Extracts all rows from the [Data] section.
    Returns a list of dictionaries where each dictionary represents a sample.
    """
    try:
        #  Find the [Data] section
        data_df = get_csv_section(file_Input_path, '[Data]')
        
        # Converts the DataFrame into a list of dictionaries
        # orient='records' --> convert each row of the DataFrame into a dictionary: {"Column1": "Value1", "Column2": "Value2", ...}
        return data_df.to_dict(orient='records')
    except Exception as e:
        print(f"Error extracting sample data from {file_Input_path}: {e}")
        return []

def process_all_csv_files(input_dir_path, output_dir_path):
    """
    Process all CSV files in a directory and extract metadata.
    Saves individual JSON files for each CSV and returns a list for the summary.
    """
    results = []
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir_path, exist_ok=True)

    # Get list of CSV files in directory
    csv_files = sorted([f for f in os.listdir(input_dir_path) if f.endswith('.csv')])
    
    # Get the total number of files for progress tracking
    total_files = len(csv_files)
    processed_count = 0
    print(f"Found {total_files} CSV files in {input_dir_path}.\n")
    for csv_file_name in csv_files:
        file_Input_path = os.path.join(input_dir_path, csv_file_name)
        
        # VALIDATION CHECK
        if not is_beadstudio_file(file_Input_path):
            print(f" BeadStudio file validation failed : {csv_file_name} does not appear to be a BeadStudio file.")
            continue # This skips the rest of the loop for THIS file
            
        print(f"BeadStudio file validated successfully. Extracting data from: {csv_file_name}")
        
        # Extract metadata
        metadata = extract_metadata(file_Input_path)
        Orid_id = extract_orid_from_filename(csv_file_name)
        if Orid_id:
            metadata["proposal_id"] = Orid_id
        manifest_id = extract_manifest_info(file_Input_path)
        num_samples = count_samples(file_Input_path)
        sample_details = extract_sample_data(file_Input_path)
        

        # Combine all information

        file_info = {
            'instrument_type': 'Illumina_iScan',
            'phase_workflow': 'Sequencing',
            'file_name': csv_file_name,
            'file_path': file_Input_path,
            'file_description': 'BeadStudio sample sheet containing array scanning configuration and per-sample metadata.',
            'metadata': metadata,
            'manifest_id': manifest_id,
            'number_of_samples': len(sample_details), # Count is now derived from the list length
            'samples': sample_details  # This adds the key-value pairs for every sample
        }
        processed_count += 1
        print(f" Processing completed for: {csv_file_name}")

        # Replace .csv with .json for the filename
        json_filename = os.path.splitext(csv_file_name)[0] + '.json'
        json_path = os.path.join(output_dir_path, json_filename)
        
        with open(json_path, 'w') as f:
            json.dump(file_info, f, indent=2)
            
        results.append(file_info)
        # Final Summary Print
    print("-" * 30)
    print(f"Batch Summary:")
    print(f"Successfully Processed: {processed_count}")
    print(f"Skipped/Failed:         {total_files - processed_count}")
    print(f"Total files checked:    {total_files}")
    print("-" * 30)
    
    return results


def one_single_file(input_file_dir_path, output_dir_path, csv_file_name):
    """
    Process one CSV file in a directory and extract metadata.
    Saves individual JSON files for each CSV and returns a list for the summary.

    # "input_file_dir_path" --> "Path to the directory containing the CSV file")
    # "csv_file_name" --> "The name of the CSV file (including .csv extension)")
    # "output_dir_path" --> "Path to the folder where results should be saved")
    """
    # Full path to the input file    
    file_Input_path = os.path.join(input_file_dir_path, csv_file_name)

    # 1. VALIDATION CHECK
    if not is_beadstudio_file(file_Input_path):
        # Raising an error and stops the execution for this specific file
        raise ValueError(f"Process aborted: {csv_file_name} is not a valid BeadStudio file.")

    print(f"BeadStudio file validation completed successfully. Extracting data from{csv_file_name}")
    
    # 2. Extraction 
    results = []
    os.makedirs(output_dir_path, exist_ok=True)

    metadata = extract_metadata(file_Input_path)
    Orid_id = extract_orid_from_filename(csv_file_name)
    if Orid_id:
            metadata["proposal_id"] = Orid_id
    manifest_id = extract_manifest_info(file_Input_path)
    num_samples = count_samples(file_Input_path)
    sample_details = extract_sample_data(file_Input_path)

    # 3. Combine all information    
    file_info = {
            'instrument_type': 'Illumina_iScan',
            'file_name': csv_file_name,
            'file_path': file_Input_path,
            'phase_workflow': 'sequencing',
            'metadata': metadata,
            'manifest_id': manifest_id,
            'number_of_samples': len(sample_details), # Count is now derived from the list length
            'samples': sample_details  # This adds the key-value pairs for every sample
        }

    # 4. Save JSON
    
    json_filename = os.path.splitext(csv_file_name)[0] + '.json'
    json_path = os.path.join(output_dir_path, json_filename)
        
    with open(json_path, 'w') as f:
        json.dump(file_info, f, indent=2)
            
    results.append(file_info)
    print(f"\n ✅ Saved Json output file to: {json_path}")
    return results



def create_summary_table(results):
    """
    Create a summary table from the extracted results.
    Returns a pandas DataFrame.
    """
    summary_data = []
    
    for result in results:
        metadata = result['metadata']
        
        summary_row = {
            'File name': result['file_name'],
            'Project name': metadata.get('project_name', 'N/A'),
            'Experiment name': metadata.get('experiment_name', 'N/A'),
            'Date': metadata.get('date', 'N/A'),
            'Manifest ID': result['manifest_id'],
            'Number of samples': result['number_of_samples']
        }
        
        summary_data.append(summary_row)
    
    return pd.DataFrame(summary_data)


def save_results(summary_table, output_dir_path):
    """
    Saves the master CSV summary table.
    """
    if output_dir_path is None:
        output_dir_path = '.'

    os.makedirs(output_dir_path, exist_ok=True)

    # Save CSV summary table
    csv_output_path = os.path.join(output_dir_path, 'metadata_BeadStudio_summary_table.csv')
    summary_table.to_csv(csv_output_path, index=False)
    print(f"\nSaved summary table to: {csv_output_path}")
    print(f"json output files saved to: {output_dir_path}")

