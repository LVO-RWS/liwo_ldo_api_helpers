"""
Gebruik dit script om nieuwe scenarios te vinden gebasseerd op afstand. Je hebt een lijst van oude scenarios nodig en een excel bestand met alle metadata.
Kies zelf waar je de resultaten wilt opslaan.

Eventueel kunnen ook andere voorwaarden toegevoegd worden aan het script zoals (nog niet geimplementeeerd):
- zelfde gebiedsnaam
- zelfde projectnaam
- zelfde frequentieklasse

"""
scenario_lijst = []
metadata_pad = ".xlsx"  #Pad naar excel met alle meta data van alle scenarios
afstand = 200 #Zoekt binnen 200 m radius
ouput_path = "nieuwe_scenarios.xlsx"

import geopandas as gpd
import pandas as pd

def bereken_afstand(x_oud, y_oud, x_nieuw, y_nieuw): 
    dx = x_nieuw - x_oud
    dy = y_nieuw - y_oud
    afstand = (dx**2 + dy**2)**0.5
    return afstand

def bepaal_frequentie(frequentie):
    if frequentie >= 10000:
        frequentie_categorie = "zelden"
    elif frequentie >= 1000:
        frequentie_categorie = "soms"
    else:
        frequentie_categorie = "vaak"
    return frequentie_categorie

# TODO: Dit is optioneel maar kan gebruikt worden voor andere analyses waarbij een scenario bij dezelfde frequentie klasse moet horen
# metadata["frequentie"] = metadata[frequentie_col].apply(bepaal_frequentie)

def bepaal_nieuw_scenario(scenario_lijst, metadata, afstand_m, output_path):

    df = pd.DataFrame({"Scenario": scenario_lijst, "frequentie_oud": None, "X": None, "Y": None, "New_scenarios": None, "afstand": None, "frequentie_nieuw": None, "X_new": None, "Y_new": None})

    # Dit zijn de kolommen in de metadata waar je de X en Y coordinaat in kan vinden, TODO: veranderen als dat anders is 
    x_col = 'x-coordinaten doorbraaklocatie/effectgebied'
    y_col = 'y-coordinaten doorbraaklocatie/effectgebied'
    frequentie_col = "Herhalingstijd buitenwater"

    ops = {
                "==": lambda k, v: metadata[k] == v,
                "!=": lambda k, v: metadata[k] != v,
                ">":  lambda k, v: metadata[k] >  v,
                ">=": lambda k, v: metadata[k] >= v,
                "<":  lambda k, v: metadata[k] <  v,
                "<=": lambda k, v: metadata[k] <= v,
            }
    
    for i in range(len(df)):
        try: 
            # Scenario nummer
            nummer = df.loc[i, "Scenario"]

            # Vind x en y coordinaat en frequentie voor oud scenario in metadata
            x_coordinaat_oud = metadata.loc[metadata["Nummer"] == nummer, x_col].values[0]
            y_coordinaat_oud = metadata.loc[metadata["Nummer"] == nummer, y_col].values[0]
            frequentie_oud = metadata.loc[metadata["Nummer"] == nummer, frequentie_col].values[0]

            # TODO: Als je een scenario wilt zoeken met een zelfde frequentie klasse gebruik dan deze code
            #frequentie_categorie_oud = bepaal_frequentie(frequentie_oud)
          
            voorwaarden = [
                # Voeg hier andere voorwaardes toe
                # ("frequentie", "==", frequentie_categorie_oud),   
                # Voorwaarde dat scenarionummer een nieuw scenario moet zijn
                ("Nummer", ">=", 100000)    
            ]
            
            # TODO: Als je een scenario wilt zoeken met een zelfde frequentie klasse gebruik dan deze code
            # metadata["frequentie"] = metadata[frequentie_col].apply(bepaal_frequentie)

            # Vind rijen in metadata die aan de voorwaarden voldoen en apply mask
            mask = pd.Series([True] * len(metadata), index=metadata.index)
            for kolom, operator, waarde in voorwaarden:
                mask &= ops[operator](kolom, waarde)

            temp_df = metadata[mask]

            # Bereken aftand
            temp_df["afstand_m"] = temp_df.apply(lambda row: bereken_afstand(x_coordinaat_oud, y_coordinaat_oud, row[x_col], row[y_col]), axis=1)

            #Selecteer punten die binnen 200 meter liggen
            scenarios_dichtbij = temp_df[temp_df["afstand_m"] < afstand_m] 

            beste_scenario = None
            afstand = None
            nieuwe_frequentie = None
            x_new = None
            y_new = None

            if not scenarios_dichtbij.empty:
                # Vind index van scenario die binnen 200 m ligt en een vergelijkbare frequentieklasse heeft
                idx = (scenarios_dichtbij[frequentie_col] - frequentie_oud).abs().idxmin()
                beste_scenario = scenarios_dichtbij["Nummer"].loc[idx]
                afstand = scenarios_dichtbij["afstand_m"].loc[idx]
                nieuwe_frequentie = scenarios_dichtbij[frequentie_col].loc[idx]
                x_new =  scenarios_dichtbij[x_col].loc[idx]
                y_new = scenarios_dichtbij[y_col].loc[idx]
            else: 
                print(f"Geen nieuw scenario gevond voor scenario: {nummer}")

            # Voeg resultaten toe aan dataframe
            df.loc[i, "X"] = x_coordinaat_oud
            df.loc[i, "Y"] = y_coordinaat_oud
            df.loc[i, "frequentie_oud"] = frequentie_oud
            df.loc[i, "New_scenarios"] = beste_scenario
            df.loc[i, "afstand"] = afstand
            df.loc[i, "frequentie_nieuw"] = nieuwe_frequentie
            df.loc[i, "X_new"] = x_new
            df.loc[i, "Y_new"] = y_new
        
        except Exception as e:
            print(f"Onverwachte fout: {e}")
            df.loc[i, "New_scenarios"] = None
            df.loc[i, "afstand"] = None
            df.loc[i, "frequentie_nieuw"] = None
            df.loc[i, "X_new"] = None
            df.loc[i, "Y_new"] = None

        df.to_excel(output_path)

    return df

bepaal_nieuw_scenario(scenario_lijst, metadata_pad, afstand, ouput_path)