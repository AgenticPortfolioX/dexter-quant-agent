
import pandas as pd

def apply_anchor_filter(df):
    """
    Applies the Anchor Filter logic (Prompt 4):
    - Anchor_Up (Long): Close > 10m 200 EMA AND Close > 1h 200 EMA
    - Anchor_Down (Short): Close < 10m 200 EMA AND Close < 1h 200 EMA
    
    Important: The 1h EMA used here comes from the shifted dataframe (Prompt 1).
    So df['EMA_200_1h'] already represents the previous completed hour's value.
    """
    try:
        # Long Filter
        df['Anchor_Up'] = (df['Close'] > df['EMA_200']) & (df['Close'] > df['EMA_200_1h'])
        
        # Short Filter
        df['Anchor_Down'] = (df['Close'] < df['EMA_200']) & (df['Close'] < df['EMA_200_1h'])
        
        return df

    except Exception as e:
        print(f"Error applying anchor logic: {e}")
        return None
