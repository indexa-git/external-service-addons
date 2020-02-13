# -*- coding: utf-8 -*-
#  Copyright (c) 2018 - Indexa SRL. (https://www.indexa.do) <info@indexa.do>
#  See LICENSE file for full licensing details.

import logging
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class CurrencyTestCase(TransactionCase):

    def setUp(self):
        super(CurrencyTestCase, self).setUp()
        self.test_company = self.env['res.company'].create({'name': 'Test Company'})
        # Each test will check the number of rates for USD
        self.currency_usd = self.env.ref('base.USD')

    def test_l10n_do_currency_update_bpd(self):
        """ Banco Popular Dominicano currency update test """

        self.test_company.l10n_do_currency_provider = 'bpd'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco Popular")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco Popular")

    def test_l10n_do_currency_update_bnr(self):
        """ Banco de Reservas currency update test """

        self.test_company.l10n_do_currency_provider = 'bnr'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco de Reservas")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco de Reservas")

    def test_l10n_do_currency_update_bpr(self):
        """ Banco del Progreso currency update test """

        self.test_company.l10n_do_currency_provider = 'bpr'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco del Progreso")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco del Progreso")

    def test_l10n_do_currency_update_bsc(self):
        """ Banco Santa Cruz currency update test """

        self.test_company.l10n_do_currency_provider = 'bsc'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco Santa Cruz")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco Santa Cruz")

    def test_l10n_do_currency_update_bdi(self):
        """ Banco BDI currency update test """

        self.test_company.l10n_do_currency_provider = 'bdi'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco BDI")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco BDI")

    def test_l10n_do_currency_update_bpm(self):
        """ Banco Promerica currency update test """

        self.test_company.l10n_do_currency_provider = 'bpm'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco Promerica")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco Promerica")

    def test_l10n_do_currency_update_bvm(self):
        """ Banco Vimenca currency update test """

        self.test_company.l10n_do_currency_provider = 'bvm'
        self.test_company.currency_base = 'buyrate'
        self.test_company.currency_service_token = 'demotoken'
        rates_count = len(self.currency_usd.rate_ids)
        res = self.test_company.l10n_do_update_currency_rates()

        if not res:
            _logger.info("No data from Banco Vimenca")

        if len(self.currency_usd.rate_ids) != (rates_count + 1):
            _logger.info("No data from Banco Vimenca")
