Dominican Banks Currency Update
===============================

Installation
============

* Go to Apps

* Search for Dominican Banks Currency Update

* Press install button

Setup
=====

Accounting Settings
-------------------

* Go to Accounting > Configuration > Settings
* Scroll to **Currency** section
* Activate Multi-currency feature
* Setup your company Dominican Bank Rates parameters like bank, interval, base and offset

Company Settings
----------------

For this module fetch data from given API, you must setup a service authentication token for each company

* Go to Settings > Users & Companies > Companies
* Select one or more companies from your companies tree view
* Click on Action > Set token

Technical Settings
----------------

You can setup the time when your currency update action will run

* Go to Settings > Automation > Scheduled Actions
* Click on **[CURRENCY] Update l10n_do banks currency** cron
* Set your time on Next Execution Date

Notes
-----
Do not change any other **Scheduled Actions** field. Your cron must run daily, even if your **Dominican Bank Rates** parameters don't.

Usage
=====
* Your **Scheduled Actions** will fetch your bank rates from the given API on intervals you set up in your settings


Support
========

Please refer to `Module Description` support contacts.