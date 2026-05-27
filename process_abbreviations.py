#!/usr/bin/env python3
import csv

def process_rg_values(rg_value, abbreviation, resolution):
    """Process RG column values and return cleaned values and info about new abbreviations."""
    if not rg_value or not rg_value.strip():
        return [], [], False
    
    values = [v.strip() for v in rg_value.split(';') if v.strip()]
    found_abbreviation = False
    new_abbreviations = set()
    contains_non_matching = False
    
    for value in values:
        if value == resolution:
            continue
        
        if value == abbreviation:
            found_abbreviation = True
        elif value.endswith('.'):
            new_abbreviations.add(value)
        else:
            contains_non_matching = True
    
    return found_abbreviation, list(new_abbreviations), contains_non_matching

def process_csv(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile, delimiter=',', quotechar='"')
        fieldnames = reader.fieldnames
        
        rows = []
        
        for row in reader:
            abbreviation = row['Abkürzung']
            resolution = row['Auflösung']
            
            rg_columns = [f'RG{i}' for i in range(1, 10)]
            
            contains_non_matching = False
            all_new_abbreviations = set()
            rg_data = {}
            
            for rg_col in rg_columns:
                found_abbreviation, new_abbrs, non_matching = process_rg_values(row[rg_col], abbreviation, resolution)
                rg_data[rg_col] = found_abbreviation
                
                all_new_abbreviations.update(new_abbrs)
                
                if non_matching:
                    contains_non_matching = True
            
            if contains_non_matching:
                rows.append(row)
                continue
            
            if all_new_abbreviations:
                for new_abbr in all_new_abbreviations:
                    new_row = row.copy()
                    new_row['Abkürzung'] = new_abbr
                    

                    for rg_col in rg_columns:
                        found_abbreviation = False
                        for value in row[rg_col].split(';'):
                            if value.strip() == new_abbr:
                                found_abbreviation = True
                        
                        new_row[rg_col] = new_abbr if found_abbreviation else ''
                    
                    rows.append(new_row)
            
            original_row = row.copy()
            for rg_col in rg_columns:
                original_row[rg_col] = abbreviation if rg_data[rg_col] else ''
            
            rows.append(original_row)
    
    with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)