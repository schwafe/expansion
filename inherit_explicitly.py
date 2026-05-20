#!/usr/bin/env python3
"""
Script to make implicit inheritance explicit in the abbreviations CSV file.
The first column value is inherited from the last line that had a value in column 1.
"""

import csv

input_file = 'data/manually_revised_abbreviations.csv'
output_file = 'temp.csv'

last_value = ''

with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8', newline='') as outfile:
    reader = csv.reader(infile)
    writer = csv.writer(outfile)
    
    # Write header as-is
    header = next(reader)
    writer.writerow(header)
    
    for row in reader:
        if row[0].strip():  # If first column has a value
            last_value = row[0]
        else:  # Inherit from last non-empty value
            row[0] = last_value
        writer.writerow(row)

print(f"Processed {input_file} -> {output_file}")
