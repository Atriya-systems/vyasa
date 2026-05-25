"""Shared pytest fixtures for the factory test suite."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


# Make sure `src/` is on sys.path so `aspireace_mocf` imports without install.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_source_data() -> dict:
    return {
        "source_id": "TEST_PHY11_001",
        "owned_sme_text": (
            "Dimensions show how a physical quantity depends on mass, length and time. "
            "Velocity is displacement divided by time, so velocity has dimension [LT^-1]. "
            "Force equals mass times acceleration, so force has dimension [MLT^-2]. "
            "Dimensional analysis can check consistency, derive relations up to "
            "dimensionless constants, and detect impossible equations."
        ),
    }


@pytest.fixture
def sample_rights_ledger_csv(tmp_path: Path) -> Path:
    csv_text = (
        "source_id,source_type,owner,commercial_use_allowed,ai_training_allowed,"
        "derivative_allowed,reference_only,license_doc,approved_for\n"
        "TEST_PHY11_001,SME_OWNED,Atriya,true,true,true,false,LIC_001.pdf,"
        '"base_subject;tutor_app;content_generator;app_content;rag;offline"\n'
        "TEST_REF_001,REFERENCE_ONLY,External,false,false,false,true,REF_LIC.pdf,""\n"
        "TEST_NO_TRAIN_001,LICENSED,External,true,false,true,false,NO_TRAIN_LIC.pdf,"
        '"app_content;rag;offline"\n'
    )
    p = tmp_path / "ledger.csv"
    p.write_text(csv_text, encoding="utf-8")
    return p


@pytest.fixture
def sample_training_record() -> dict:
    return {
        "text": (
            "Dimensional analysis is a powerful tool for checking the consistency "
            "of equations in physics. By comparing the dimensions of each term, we "
            "can detect errors that pure numerical checks might miss. For example, "
            "if a derived formula gives length divided by velocity, the result must "
            "have units of time, not energy."
        ),
        "metadata": {
            "record_id": "BASE_PHY_001",
            "source_unit_id": "PHY11_CH01_U001",
            "lane": "base_subject",
            "record_type": "base_note",
            "quality_status": "draft",
            "train_allowed": False,
            "drafted_by": "api_model",
        },
    }


@pytest.fixture
def sample_tutor_record() -> dict:
    return {
        "messages": [
            {
                "role": "user",
                "content": "How do I check whether my derived formula is correct?",
            },
            {
                "role": "assistant",
                "content": (
                    "Start with dimensional analysis. Write out the dimensions of each "
                    "term in your equation. Every term in an equation must have the "
                    "same dimensions. If they do not match, your formula has an error. "
                    "This catches algebra mistakes without requiring you to find them by "
                    "trial and error."
                ),
            },
        ],
        "metadata": {
            "record_id": "TUTOR_PHY_001",
            "source_unit_id": "PHY11_CH01_U001",
            "lane": "tutor_app",
            "record_type": "doubt_hint_misconception_revision",
            "quality_status": "draft",
            "train_allowed": False,
            "drafted_by": "api_model",
        },
    }


@pytest.fixture
def sample_app_card_record() -> dict:
    return {
        "card_id": "NOTE_PHY11_CH01_U001_001",
        "source_unit_id": "PHY11_CH01_U001",
        "card_type": "notes_card",
        "surface": "NOTES_BUILDER",
        "title": "Why dimensional analysis works",
        "body": (
            "Dimensional analysis works because the units of physical quantities are "
            "themselves invariants. No matter what numbers you plug in, the dimensions "
            "on both sides of a correct equation must match. This makes dimensional "
            "analysis a fast first-pass check on any derived formula before doing the "
            "full algebraic work."
        ),
        "metadata": {
            "lane": "notes",
            "source_id": "TEST_PHY11_001",
            "quality_status": "draft",
            "train_allowed": False,
            "drafted_by": "api_model",
            "subject": "Physics",
            "class_level": "11",
            "chapter_no": 1,
            "chapter_name": "Units and Measurements",
            "topic": "Dimensional Analysis",
            "subtopic": "Why it works",
        },
    }
