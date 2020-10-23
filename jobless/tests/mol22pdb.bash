which babel > /dev/null || (echo 'Babel not found' > /dev/stderr; exit 1)
babel -i mol2 mol2_file -o pdb RESULT
