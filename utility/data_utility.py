# Data cleaning utility functions for NextStrain's open data
# Data available at  https://docs.nextstrain.org/projects/ncov/en/latest/reference/remote_inputs.html

import polars as pl
from datetime import timedelta


# Clean the clade data from NextStrain
def data_prep(dataf):
    """
    Filter a line list data file and summarize to get clade counts
    
    1) Filter out data we won't use
        i) only homo-sapiens
        ii) only USA
        iii) date is not null
        iv) only normal states
        v) only clade, date collection date, sequence date, state
        vi) (Optional) most recent date
    
    Parameters
    ----------
    dataf : data frame
        Line list data set
    
    Returns
    -------
    data frame
        Columns are ``location``, ``date``, ``clade``, ``count``
    """
    # columns to keep
    cols = [
        "clade_nextstrain",
        "country",
        "division",
        "host",
        "date"
    ]
    
    # There are some other odd divisions in the data, but these are the lower 48 states and DC
    states = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", 
        "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", 
        "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", 
        "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", 
        "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", 
        "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", 
        "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "Washington DC"
    ]

    # This does some general tidying
    df = (
        dataf.cast({"date" : pl.Date}, strict=False)
        .select(cols)
        .filter(
            pl.col("country") == "USA",
            pl.col("division").is_in(states),
            pl.col("date").is_not_null(),
            pl.col("host") == "Homo sapiens"
        )
        .rename({
            "clade_nextstrain": "clade",
            "division": "location"
        })
    )

    # Now collect the 1 obs per line into counts
    counts_dat = (
        df.sort("date")
        .group_by("location", "date", "clade")
        .agg(pl.len().alias("count"))
        .sort("date")
    )
    
    return counts_dat


# Determine list of variants to model
def clades_to_model(dataf, threshold = .01, threshold_weeks = 3):
    """
    Determine list of clades to model
    
    Parameters
    ----------
    dataf : data frame
        Line list data set
    threshold : float
        Clades that account for at least ``threshold`` proportion of reported
        sequences are candidates for inclusion.
    threshold_weeks : int
        The number of weeks that we look back to identify clades.
    
    Returns
    -------
    list of strings
        
    """
    
    # What is the most recent day of data
    max_day = dataf['date'].max()

    # Get the week start three weeks ago (not including this week)
    three_sundays_ago = max_day - timedelta(days = max_day.weekday() + 7*(threshold_weeks))

    # sum over weeks, combine states, and limit to just the past 3 weeks (not including current week)
    df = (
        dataf.filter(pl.col("date") >= three_sundays_ago)
        .group_by_dynamic("date", every="1w", start_by = "sunday", group_by="clade")
        .agg(pl.col("count").sum())
    )
    
    # Create a smaller data frame with the total counts per week
    total_counts = df.group_by("date").agg(pl.col("count").sum().alias("total_count"))
    
    #Join with count data to add a total counts per day column
    prop_dat = (
        df.join(total_counts, on="date")
        .with_columns((pl.col("count")/pl.col("total_count")).alias("proportion"))
    )
    
    # Retrieve list of variants which have crossed the threshold over the past threshold_weeks weeks
    high_prev_variants = (
        prop_dat.filter(pl.col("proportion") > threshold)
        .get_column("clade")
        .unique()
        .to_list()
    )

    # If more than 9 clades cross the threshold, we take the 9 with the largest counts over the past threshold_weeks weeks
    if len(high_prev_variants) > 9:
        high_prev_variants = (
            prop_dat.group_by("clade")
            .agg(pl.col("count").sum())
            .sort("count")
            .get_column("clade")
            .to_list()[:9]
        )

    return(high_prev_variants)
