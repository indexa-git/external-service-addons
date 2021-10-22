import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate_old_fields(env):
    """
    can_validate_rnc   ---->   l10_do_can_validate_rnc
    """

    env.cr.execute(
        """
        SELECT EXISTS(
            SELECT
            FROM information_schema.columns
            WHERE table_name = 'res_company'
            AND column_name = 'can_validate_rnc'
        );
        """
    )
    if env.cr.fetchone()[0] or False:
        _logger.info(
            """
            Migrating fields:
            can_validate_rnc    ---->   l10_do_can_validate_rnc
            """
        )
        for company in env["res.company"].search([]):
            query = """
            UPDATE res_company
            SET l10_do_can_validate_rnc = can_validate_rnc
            WHERE id = %s;
            """
            env.cr.execute(query % company.id)

        _logger.info("Dropping deprecated columns")
        drop_query = """
        ALTER TABLE res_company
        DROP COLUMN can_validate_rnc;
        """
        env.cr.execute(drop_query)


def migrate(cr, version):

    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_old_fields(env)
