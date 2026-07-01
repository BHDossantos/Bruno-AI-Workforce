"""Insurance quote-intake templates.

When a prospect replies asking for insurance, we reply with the exact info needed
to quote that line. This holds, per quote type (Personal Auto, Commercial Auto,
Workers' Comp, General Liability): the English requirements checklist and a
ready-to-send draft quotation email (English + Portuguese, since much of the book
is Brazilian-Portuguese). Pure data — safe to read anywhere.
"""
from __future__ import annotations

QUOTE_TYPES: list[dict] = [
    {
        "key": "personal_auto",
        "label": "Personal Auto",
        "line": "auto",
        "requirements": [
            "Driver's license for everyone who may drive the vehicle "
            "(check whether any driver has an out-of-state or foreign license — if so, include it too)",
            "Correct address where the vehicle is kept",
            "Vehicle VIN",
            "Finance company (lienholder), if the vehicle is already financed",
        ],
        "email_subject": "Your auto insurance quote — a few quick details",
        "email_body_en": (
            "Hi there,\n\n"
            "Thanks for reaching out — I'd be glad to get you an auto insurance quote. "
            "To put together an accurate quote, could you send me the following?\n\n"
            "1. Driver's license for everyone who will drive the vehicle "
            "(if any driver has an out-of-state or foreign license, please include that too)\n"
            "2. The correct address where the vehicle is kept\n"
            "3. The vehicle's VIN\n"
            "4. If the vehicle is financed, the name of the finance company (lienholder)\n\n"
            "As soon as I have these, I'll get your quote back to you quickly."
        ),
        "email_body_pt": (
            "Olá,\n\n"
            "Obrigado pelo contato — terei prazer em preparar sua cotação de seguro auto. "
            "Para fazer uma cotação precisa, poderia me enviar o seguinte?\n\n"
            "1. Carteira de motorista de todos que possam dirigir o veículo "
            "(se alguém tiver carteira de fora/estrangeira, envie junto)\n"
            "2. Endereço correto onde o veículo fica\n"
            "3. VIN do veículo\n"
            "4. Financiadora, caso o veículo já seja financiado\n\n"
            "Assim que eu tiver essas informações, retorno com sua cotação rapidamente."
        ),
    },
    {
        "key": "commercial_auto",
        "label": "Commercial Auto (CAP)",
        "line": "commercial",
        "requirements": [
            "Company EIN",
            "Type of service the company performs",
            "Driver's license for everyone who may drive the vehicle "
            "(include any out-of-state or foreign licenses)",
            "Correct company address (it may be outdated at the RMV or MassCorp — please confirm the current one)",
            "Vehicle VIN",
            "Finance company (lienholder), if any",
            "For motor truck insurance: the cargo values and the limits required by the company you contract with",
        ],
        "email_subject": "Your commercial auto quote — details needed",
        "email_body_en": (
            "Hi there,\n\n"
            "Happy to quote your commercial auto policy. To get you an accurate quote, please send:\n\n"
            "1. Company EIN\n"
            "2. The type of service your company performs\n"
            "3. Driver's license for everyone who may drive the vehicle "
            "(include any out-of-state or foreign licenses)\n"
            "4. The correct company address (it can be outdated at the RMV or MassCorp — please confirm the current one)\n"
            "5. The vehicle's VIN\n"
            "6. If financed, the finance company (lienholder)\n"
            "7. If this is motor truck insurance: the cargo values and the limits required by the company you contract with\n\n"
            "Once I have these, I'll turn your quote around quickly."
        ),
        "email_body_pt": (
            "Olá,\n\n"
            "Terei prazer em cotar seu seguro comercial de veículo (CAP). "
            "Para uma cotação precisa, envie por favor:\n\n"
            "1. EIN da companhia\n"
            "2. Tipo de serviço feito pela companhia\n"
            "3. Carteira de motorista de todos que possam dirigir o veículo "
            "(inclua carteiras de fora/estrangeiras, se houver)\n"
            "4. Endereço correto da companhia (pode estar desatualizado na RMV ou no Mass Corp — confirme o atual)\n"
            "5. VIN do veículo\n"
            "6. Financiadora, caso já tenha\n"
            "7. Em caso de motor truck insurance: valores de cargo e limites exigidos pela contratante\n\n"
            "Assim que eu tiver isso, retorno com sua cotação rapidamente."
        ),
    },
    {
        "key": "workers_comp",
        "label": "Workers' Compensation (WC)",
        "line": "commercial",
        "requirements": [
            "Company EIN",
            "Number of employees — ask whether the owner also works (i.e. owner + number of employees)",
            "Detailed description of the work the company does "
            "(just \"carpentry\" or \"construction\" is not enough for a quote)",
            "Desired payroll",
            "(Good moment to explain the year-end audit to the client)",
        ],
        "email_subject": "Your workers' comp quote — a few details",
        "email_body_en": (
            "Hi there,\n\n"
            "Glad to help with workers' compensation. To quote accurately, I'll need:\n\n"
            "1. Company EIN\n"
            "2. Number of employees — and please let me know if the owner also works "
            "(i.e. owner + number of employees)\n"
            "3. A detailed description of the work your company does — \"carpentry\" or "
            "\"construction\" alone isn't enough; the more specific, the better\n"
            "4. Your desired payroll\n\n"
            "One quick note: workers' comp premiums are audited at the end of the term based on "
            "actual payroll, so the initial quote is an estimate — happy to explain how the audit works."
        ),
        "email_body_pt": (
            "Olá,\n\n"
            "Terei prazer em ajudar com o Workers' Comp. Para cotar com precisão, vou precisar de:\n\n"
            "1. EIN da companhia\n"
            "2. Quantos funcionários — e me diga se o dono também trabalha (ou seja, dono + funcionários)\n"
            "3. Descrição detalhada do serviço feito pela companhia — só \"carpentry\" ou "
            "\"construction\" não é suficiente; quanto mais específico, melhor\n"
            "4. Payroll desejado\n\n"
            "Uma observação: o prêmio do Workers' Comp é auditado no fim do período com base no "
            "payroll real, então a cotação inicial é uma estimativa — posso explicar como funciona a auditoria."
        ),
    },
    {
        "key": "general_liability",
        "label": "General Liability (GL)",
        "line": "commercial",
        "requirements": [
            "Company EIN",
            "Number of employees — ask whether the owner also works (i.e. owner + number of employees)",
            "Detailed description of the work the company does "
            "(just \"carpentry\" or \"construction\" is not enough for a quote)",
            "Desired payroll",
        ],
        "email_subject": "Your general liability quote — a few details",
        "email_body_en": (
            "Hi there,\n\n"
            "Happy to quote your general liability coverage. To get an accurate quote, please send:\n\n"
            "1. Company EIN\n"
            "2. Number of employees — and whether the owner also works (owner + number of employees)\n"
            "3. A detailed description of the work your company does — just \"carpentry\" or "
            "\"construction\" isn't enough; specifics help\n"
            "4. Your desired payroll\n\n"
            "Once I have these, I'll get your quote right over."
        ),
        "email_body_pt": (
            "Olá,\n\n"
            "Terei prazer em cotar sua General Liability. Para uma cotação precisa, envie por favor:\n\n"
            "1. EIN da companhia\n"
            "2. Quantos funcionários — e se o dono também trabalha (dono + funcionários)\n"
            "3. Descrição detalhada do serviço feito pela companhia — só \"carpentry\" ou "
            "\"construction\" não basta; detalhes ajudam\n"
            "4. Payroll desejado\n\n"
            "Assim que eu tiver isso, retorno com sua cotação."
        ),
    },
]

_BY_KEY = {q["key"]: q for q in QUOTE_TYPES}


def all_templates() -> list[dict]:
    return QUOTE_TYPES


def get(key: str) -> dict | None:
    return _BY_KEY.get(key)
