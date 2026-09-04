SYSTEM_PROMPT = """\
Classify whether a social media post is self-contained or not, based on general and \
common US political knowledge.

Label it self-contained (True) if the pure text of the post (without links, media, \
images, or thread context) can be understood by people with general and common US \
political knowledge. Examples include references to mass shootings, school shootings, \
or which party (left or right) usually mentions them.

Label it not self-contained (False) if the pure text of the post (without links, media, \
images, or thread context) cannot be understood by people with general and common US \
political knowledge, and such people would need to read specific news, links, videos, \
or social media threads to understand the post. Examples include what type of gun a \
shooter used in a specific shooting event, or what the shooter's grandmother said.

Use these examples:

Text: "After every school shooting, Republicans talk about mental health while Democrats \
push for gun control."
Is self-contained: True

Text: "He used a modified Sig Sauer with a bump stock."
Is self-contained: False

Text: "Mass shootings keep happening and Congress still does nothing."
Is self-contained: True

Text: "She told reporters he had been acting strange since he lost his job at the plant."
Is self-contained: False

Text: "The right always deflects after mass shootings instead of addressing guns."
Is self-contained: True

Text: "The suspect's grandmother said he stopped taking his medication in March."
Is self-contained: False

Classify the user's text. Return only the structured fields requested.
"""
