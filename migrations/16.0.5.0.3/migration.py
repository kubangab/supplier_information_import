def migrate(cr, version):
    cr.execute("""
        ALTER TABLE import_column_mapping
        ADD COLUMN IF NOT EXISTS is_required boolean DEFAULT false
    """)