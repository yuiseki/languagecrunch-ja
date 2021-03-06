import logging
from textblob import TextBlob

# from countries_tagger import RESTCountriesComponent
from sentence_classifier import SentenceTypeClassifier

logging.basicConfig(level=logging.INFO)

__author__ = 'parth.mudgal'
from bottle import route, run, request
from sympy import *
from sympy.stats import Normal
import spacy
import sys
from nltk.corpus import wordnet as wn
from numpy import dot, unicode
from numpy.linalg import norm

cosine = lambda v1, v2: dot(v1, v2) / (norm(v1) * norm(v2))

logging.info("Loading spacy model, wait for confirmation before using")
nlp = spacy.load('ja_ginza')
logging.info("Loaded spacy model")


def get_sentence_entities(doc):
    return [{"text": entity.text, "label": entity.label_} for entity in doc.ents]


def get_similar_words(word, count):
    apple = nlp.vocab[word]

    others = list({w for w in nlp.vocab if w.has_vector and w.orth_.islower() and w.lower_ != unicode(word)})

    # sort by similarity score
    others.sort(key=lambda w: cosine(w.vector, apple.vector))
    others.reverse()

    return [{"word": word.orth_ for word in others[:count]}]


def hash_token(token):
    hash = ":".join([c.text for c in token.rights]) + token.text + ":".join([c.text for c in token.lefts])
    return hash
    pass


def get_sentence_pos(doc):
    i = 0
    tokenIdMap = {}
    for sent in doc.sents:
        for token in sent:
            i = i + 1
            tokenHash = hash_token(token)
            tokenIdMap[tokenHash] = i

    return [
        {
            "sentence": sent.string,
            "sentiment": TextBlob(sent.string).sentiment,
            "root": {
                "text": sent.root.string,
                "orth": tokenIdMap[hash_token(sent.root)],
            },
            "pos": [
                {
                    "text": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "tag": token.tag_,
                    "dep": token.dep_,
                    "ent": token.ent_type_,
                    "orth": tokenIdMap[hash_token(token)],
                    "is_oov": token.is_oov,
                    "conjuncts": [{
                        "text": t.text,
                        "orth": tokenIdMap[hash_token(t)],
                    } for t in token.conjuncts],
                    "shape": token.shape_,
                    "left": [{"text": r.text, "orth": tokenIdMap[hash_token(r)]} for r in token.lefts],
                    "right": [{"text": r.text, "orth": tokenIdMap[hash_token(r)]} for r in token.rights],
                    "is_alpha": token.is_alpha,
                    "is_stop": token.is_stop,
                } for token in sent
            ],
            "sentence_type": SentenceTypeClassifier(sent)
        } for sent in doc.sents
    ]


def parse_sentence():
    se = request.query.getunicode('sentence')
    logging.info('parse sentence', se)
    doc1 = nlp(se)
    sents = doc1.sents
    for sent in sents:
        logging.info(sent, " -> ", sent.root)


@route('/nlp/parse', method="GET")
def nlp_everything():
    se = request.query.getunicode('sentence')
    logging.info('parse sentence %s', se)
    doc = nlp(se)
    relations = extract_semantic_relations(doc)
    sentences = get_sentence_pos(doc)
    entities = get_sentence_entities(doc)
    return {
        "relations": relations,
        "sentences": sentences,
        "entities": entities,
    }


@route('/', method="GET")
@route('/health', method="GET")
def health_check():
    return {
        "status": "ok"
    }


@route('/nlp/spellcheck', method="GET")
def spellcheck():
    sentence = request.query.getunicode('sentence')
    b = TextBlob(sentence)
    correct_string = b.correct()
    correct = correct_string == sentence
    return {
        "original": sentence,
        "corrected": correct_string.string,
        "correct": correct,
    }


cache = {}


@route('/nlp/word', method="GET")
def nlp_everything():
    word = request.query.getunicode('word')
    pos = request.query.getunicode('pos')

    logging.info('lookup word %s -- %s' % (word, pos))

    hash_key = '%s.%s' % (word, pos)
    if hash_key in cache:
        return cache[hash_key]

    synsets = wn.synsets(word, pos=pos)
    # similar_words = get_similar_words(word, 10)

    results = []

    for synset in synsets:
        results.append({
            "definition": synset.definition(),
            "examples": synset.examples(),
            "lemma_names": synset.lemma_names(),
            # "lex_name": synset.lex_name,
            "hypernyms": [
                {
                    "definition": hypern.definition(),
                    "examples": hypern.examples(),
                    "lemma_names": hypern.lemma_names(),
                } for hypern in synset.hypernyms()
            ],
            "lemmas": [
                {
                    "frame_strings": lemma.frame_strings(),
                    "name": lemma.name(),
                    # "similar_words": get_similar_words(lemma.name(), 10),
                    "frame_ids": lemma.frame_ids(),
                    "hypernyms": [
                        {
                            "definition": hypern.definition(),
                            "examples": hypern.definition(),
                            "lemma_names": hypern.definition(),
                        } for hypern in lemma.hypernyms()
                    ],
                    "hyponyms": [
                        {
                            "definition": hyponym.definition(),
                            "examples": hyponym.definition(),
                            "lemma_names": hyponym.definition(),
                        } for hyponym in lemma.hyponyms()
                    ],
                } for lemma in synset.lemmas()
            ],
            "hyponyms": [
                {
                    "definition": hyponym.definition(),
                    "examples": hyponym.examples(),
                    "lemma_names": hyponym.lemma_names(),
                } for hyponym in synset.hyponyms()
            ],

        })

    response = {"results": results}
    cache[hash_key] = response

    return response

# extend https://github.com/explosion/spacy/blob/master/examples/information_extraction/entity_relations.py for all entities

def extract_semantic_relations(doc):
    # merge entities and noun chunks into one token
    for span in [*list(doc.ents), *list(doc.noun_chunks)]:
        span.merge()

    entities = ["PERSON", "NORP",
                "FACILITY", "ORG",
                "GPE", "LOC",
                "PRODUCT", "EVENT",
                "WORK_OF_ART", "LAW",
                "LANGUAGE", "DATE",
                "TIME", "PERCENT",
                "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"]
    relations = []
    for entity_name in entities:
        for money in filter(lambda w: w.ent_type_ == entity_name, doc):
            if money.dep_ in ('attr', 'dobj', 'acomp'):
                subject = [w for w in money.head.lefts if w.dep_ == 'nsubj']
                if subject:
                    subject = subject[0]
                    relations.append({"subject": subject.string.strip(), "object": money.string.strip(), "relation": entity_name})
                else:
                    subject = "N/A"
                    relations.append({"subject": "N/A", "object": money.string.strip(), "relation": entity_name})

            elif money.dep_ == 'pobj' and money.head.dep_ == 'prep':
                relations.append({"subject": money.head.head.string.strip(), "object": money.string.strip(), "relation": entity_name})
    return relations


run(host='0.0.0.0', port=sys.argv[1])
