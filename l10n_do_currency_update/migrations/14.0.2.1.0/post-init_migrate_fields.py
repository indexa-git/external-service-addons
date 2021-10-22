import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate_old_fields(env):
    """
    currency_base                  ---->   l10n_do_currency_base
    rate_offset                    ---->   l10n_do_rate_offset
    last_currency_sync_date        ---->   l10n_do_last_currency_sync_date
    """

    env.cr.execute(
        """
        SELECT EXISTS(
            SELECT
            FROM information_schema.columns
            WHERE table_name = 'res_company'
            AND column_name IN (
                'currency_base',
                'rate_offset',
                'last_currency_sync_date'
            )
        );
        """
    )
    if env.cr.fetchone()[0] or False:
        _logger.info(
            """
            Migrating fields:
            currency_base                  ---->   l10n_do_currency_base
            rate_offset                    ---->   l10n_do_rate_offset
            last_currency_sync_date        ---->   l10n_do_last_currency_sync_date
            """
        )
        for company in env["res.company"].search([]):
            query = """
            UPDATE res_company
            SET l10n_do_currency_base = currency_base,
            l10n_do_rate_offset = rate_offset,
            l10n_do_last_currency_sync_date = last_currency_sync_date
            WHERE id = %s;
            """
            env.cr.execute(query % company.id)

        _logger.info("Dropping deprecated columns")
        drop_query = """
        ALTER TABLE res_company
        DROP COLUMN currency_base,
        DROP COLUMN rate_offset,
        DROP COLUMN last_currency_sync_date;
        """
        env.cr.execute(drop_query)


def migrate(cr, version):

    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_old_fields(env)
